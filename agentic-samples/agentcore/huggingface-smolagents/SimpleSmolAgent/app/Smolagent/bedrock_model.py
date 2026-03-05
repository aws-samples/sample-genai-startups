"""Bedrock Converse model adapter for smolagents ToolCallingAgent.

smolagents' AmazonBedrockModel has a known bug where the parent ApiModel appends
OpenAI-style 'tools' and 'tool_choice' to the request kwargs, and AmazonBedrockModel
only removes 'toolConfig' but never removes those — causing Bedrock's converse() API
to reject them with a parameter validation error.

Upstream fix: https://github.com/huggingface/smolagents/pull/1661
(open since Aug 2025, not yet merged as of Mar 2026 — remove this file and switch
back to AmazonBedrockModel once that PR lands)

This wrapper calls converse() directly via boto3, puts tools in toolConfig (the correct
Bedrock format), and parses toolUse response blocks into ChatMessageToolCall objects.

Message history notes
---------------------
smolagents ToolCallingAgent reconstructs conversation history via ActionStep.to_messages(),
which does NOT preserve structured tool_calls on the assistant message. Instead it emits:
  - role="tool-call"     → text: "Calling tools: [...]"   (no tool_calls attribute)
  - role="tool-response" → text: "Observation: ..."        (no tool_call_id attribute)

These must be mapped to plain text turns (assistant / user) rather than toolUse / toolResult
blocks to satisfy Bedrock's constraint that every toolResult must match a preceding toolUse.
Consecutive messages of the same Bedrock role are merged so the conversation alternates.
"""
import json
import boto3
from typing import Any, List, Optional

from smolagents.models import ChatMessage, ChatMessageToolCall, ChatMessageToolCallFunction, MessageRole


class BedrockConverseModel:
    """smolagents-compatible model that calls Bedrock Converse API via boto3.

    Designed for use with ToolCallingAgent. Uses the runtime IAM role in deployed
    environments — no API keys needed.

    Args:
        model_id: Bedrock model ID (e.g. "anthropic.claude-sonnet-4-5-20250929-v1:0").
        region_name: AWS region where Bedrock is available.
    """

    def __init__(self, model_id: str, region_name: str = "us-east-1"):
        self.model_id = model_id
        self._client = boto3.client("bedrock-runtime", region_name=region_name)

    @staticmethod
    def _attr(obj, key):
        return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)

    def _to_bedrock_messages(self, messages: List) -> tuple:
        bedrock: list = []
        system: Optional[list] = None

        for msg in messages:
            role = self._attr(msg, "role")
            content = self._attr(msg, "content")
            tool_calls = self._attr(msg, "tool_calls")
            tool_call_id = self._attr(msg, "tool_call_id")

            if hasattr(role, "value"):
                role = role.value

            # --- system ---
            if role == "system":
                if isinstance(content, list):
                    text = " ".join(
                        b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                else:
                    text = content or ""
                system = [{"text": text}]
                continue

            # --- role mapping ---
            # "tool-call" comes from ActionStep.to_messages() as a plain-text assistant
            # description of what was called — no structured tool_calls attribute.
            # Map it to the assistant role so it follows an assistant turn or can be merged.
            if role == "tool-call":
                bedrock_role = "assistant"
            elif role in ("assistant",):
                bedrock_role = "assistant"
            else:
                bedrock_role = "user"

            # --- build content blocks ---
            blocks: list = []

            if role == "tool-response":
                if tool_call_id:
                    # Structured tool result (rare with ToolCallingAgent; kept for completeness).
                    blocks.append({
                        "toolResult": {
                            "toolUseId": tool_call_id,
                            "content": [{"text": str(content or "")}],
                        }
                    })
                else:
                    # ActionStep.to_messages() observation — plain text, no tool_call_id.
                    # Must NOT be a toolResult block; send as plain text so Bedrock does not
                    # require a matching toolUse in the previous assistant turn.
                    if isinstance(content, list):
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "text":
                                blocks.append({"text": b.get("text", "")})
                    elif isinstance(content, str) and content:
                        blocks.append({"text": content})
            else:
                # Text content
                if isinstance(content, str) and content:
                    blocks.append({"text": content})
                elif isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "text":
                            blocks.append({"text": b.get("text", "")})

                # Structured tool calls (present on the live assistant message from generate())
                if tool_calls:
                    for tc in tool_calls:
                        fn = tc.get("function", tc) if isinstance(tc, dict) else getattr(tc, "function", tc)
                        name = fn.get("name", "") if isinstance(fn, dict) else getattr(fn, "name", "")
                        args = fn.get("arguments", {}) if isinstance(fn, dict) else getattr(fn, "arguments", {})
                        tc_id = tc.get("id", "tc") if isinstance(tc, dict) else getattr(tc, "id", "tc")
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        blocks.append({"toolUse": {"toolUseId": tc_id, "name": name, "input": args}})

            if not blocks:
                continue

            # Merge consecutive same-role messages — Bedrock requires strict alternation.
            if bedrock and bedrock[-1]["role"] == bedrock_role:
                bedrock[-1]["content"].extend(blocks)
            else:
                bedrock.append({"role": bedrock_role, "content": blocks})

        return bedrock, system

    _VALID_JSON_SCHEMA_TYPES = {"string", "number", "integer", "boolean", "array", "object", "null"}

    def _to_bedrock_tools(self, tools: List) -> list:
        result = []
        for t in tools:
            inputs = getattr(t, "inputs", {}) or {}
            properties = {}
            for p, s in inputs.items():
                prop: dict = {}
                if isinstance(s, dict):
                    raw_type = s.get("type", "string")
                    if raw_type in self._VALID_JSON_SCHEMA_TYPES:
                        prop["type"] = raw_type
                    desc = s.get("description", "")
                    if desc:
                        prop["description"] = desc
                else:
                    prop["type"] = "string"
                properties[p] = prop
            result.append({
                "toolSpec": {
                    "name": getattr(t, "name", str(t)),
                    "description": getattr(t, "description", "") or "",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": properties,
                            "required": list(inputs.keys()),
                        }
                    },
                }
            })
        return result

    def generate(
        self,
        messages: List,
        stop_sequences: Optional[List[str]] = None,
        response_format: Optional[Any] = None,
        tools_to_call_from: Optional[List] = None,
        **kwargs: Any,
    ) -> ChatMessage:
        bedrock_msgs, system = self._to_bedrock_messages(messages)

        kwargs: dict = {"modelId": self.model_id, "messages": bedrock_msgs}
        if system:
            kwargs["system"] = system
        if stop_sequences:
            kwargs["inferenceConfig"] = {"stopSequences": stop_sequences}
        if tools_to_call_from:
            kwargs["toolConfig"] = {"tools": self._to_bedrock_tools(tools_to_call_from)}

        response = self._client.converse(**kwargs)
        output = response["output"]["message"]

        text_parts: list = []
        tool_calls: list = []
        for block in output.get("content", []):
            if "text" in block:
                text_parts.append(block["text"])
            elif "toolUse" in block:
                tu = block["toolUse"]
                tool_calls.append(
                    ChatMessageToolCall(
                        id=tu["toolUseId"],
                        type="function",
                        function=ChatMessageToolCallFunction(
                            name=tu["name"],
                            arguments=tu["input"],
                        ),
                    )
                )

        return ChatMessage(
            role=MessageRole.ASSISTANT,
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls or None,
        )
