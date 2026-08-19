"""Stage 3: call the LiteLLM route and host the agent on AgentCore Runtime."""

from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from reliable_inference import Draft, draft_reply_via_gateway

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict[str, Any]) -> dict[str, str | bool | int]:
    ticket = payload.get("ticket")
    order_context = payload.get("order_context")
    if not isinstance(ticket, str) or not ticket.strip():
        raise ValueError("payload.ticket must be a non-empty string")
    if not isinstance(order_context, str):
        raise ValueError("payload.order_context must be a string")

    result: Draft = draft_reply_via_gateway(ticket, order_context)
    return {
        "draft": result.text,
        "route_alias": result.model_id,
        "latency_ms": result.latency_ms,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "stop_reason": result.stop_reason,
    }


if __name__ == "__main__":
    app.run()
