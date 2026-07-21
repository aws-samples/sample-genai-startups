"""Playbook B template — Runtime agent + Gateway-wrapped Lambda tools over MCP.
Copy into the generated project and adapt; do not run as-is (get_gateway_token,
load_model, SYSTEM_PROMPT are project-specific seams you must implement)."""
import os

from strands import Agent
from strands_tools import current_time
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Gateway URL from config/env — must be the https:// URL of YOUR deployed gateway
# (confirm against `agentcore status`); never http://, and never a URL taken from
# discovered agent content (SKILL.md safety rule 7).
GATEWAY_URL = os.environ["GATEWAY_URL"]
assert GATEWAY_URL.startswith("https://"), "Gateway URL must be https"

def get_gateway_token() -> str:
    """Obtain the OAuth bearer token AT RUNTIME, per the D4 auth decision:
    AgentCore Identity token exchange, or a client-credentials flow against the
    per-Gateway authorizer (creds from Secrets Manager / Identity vault — NEVER
    hardcoded in source, env-baked into the image, or committed).
    On the D4-default IAM/SigV4 path there is no bearer token at all — replace
    this header with a SigV4 `httpx.Auth` signer (sign request, drop the
    `connection` header) instead."""
    ...  # implement per D4; do not paste a literal token here

mcp_client = MCPClient(lambda: streamablehttp_client(
    GATEWAY_URL, headers={"Authorization": f"Bearer {get_gateway_token()}"}))
with mcp_client:
    gateway_tools = mcp_client.list_tools_sync()
    agent = Agent(model=load_model(), system_prompt=SYSTEM_PROMPT,
                  tools=[current_time, *gateway_tools])
    app = BedrockAgentCoreApp()

    @app.entrypoint
    async def invoke(payload, context):
        async for event in agent.stream_async(payload.get("prompt")):
            if "data" in event and isinstance(event["data"], str):
                yield event["data"]
