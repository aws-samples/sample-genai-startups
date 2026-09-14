"""Alternate entrypoint: Runtime + AgentCore Gateway + original Lambdas.

This file is the middle migration path called out in the blog. The Strands
agent runs in the AgentCore Runtime container (same as main.py), but instead
of inlining the tool business logic as @tool functions it connects to an
AgentCore Gateway over MCP and lets the Gateway dispatch to the unchanged
Phase 1 Lambdas.

Use this file when:
  * You want to preserve existing Lambdas (IAM, CI/CD, on-call) during the
    first migration step.
  * You plan to inline the tools later, but not on day one.

Swap this in for main.py by pointing the AgentCore Runtime entrypoint at
this file (set `entrypoint` in agentcore/agentcore.json to
`app/PrivateAviationAgent/main_gateway.py`).

Required environment variables:
  GATEWAY_MCP_URL         — the MCP endpoint of the AgentCore Gateway
  GATEWAY_CLIENT_ID       — Cognito client id the Gateway authorizer accepts
  GATEWAY_CLIENT_SECRET   — matching client secret
  GATEWAY_TOKEN_ENDPOINT  — Cognito hosted token endpoint
  GATEWAY_SCOPE           — OAuth2 scope, e.g. "<gateway-name>/invoke"

The Gateway and its three Lambda targets are created exactly the same way
Phase 3 (3-agentcore-harness/Makefile) creates them — see `agentcore add
gateway` and `agentcore add gateway-target` in that Makefile for a
non-interactive reference.
"""
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx
from strands import Agent
from strands.models import BedrockModel
from strands_tools import current_time
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.runtime import BedrockAgentCoreApp


SYSTEM_PROMPT = """You are an AI assistant for a private aviation company. You help book private jet
reservations for aircraft owners and their families.

When a user requests a trip:
1. Look up the owner's information using their owner ID to find their home airport.
2. Look up the owner's registered passengers (family members).
3. Determine the departure airport (owner's home airport) and arrival airport based on the destination.
4. Compute the flight date/time based on the user's request.
5. Book the reservation with all passengers.

Important:
- Disney World is near Orlando, Florida. The nearest airport is KMCO (Orlando International).
- Always use ICAO airport codes (e.g., KJFK, KMCO, KLAX).
- When the user says "family", include all registered passengers for the owner.
- Format dates in ISO 8601 format.
"""


# ── OAuth2 token caching ─────────────────────────────────────────────────
_token_cache: dict = {"token": None, "expires_at": None}


def _fetch_bearer_token() -> str:
    """Cache the Cognito access token and refresh 5 minutes before expiry."""
    now = datetime.now()
    if (_token_cache["token"]
            and _token_cache["expires_at"]
            and now < _token_cache["expires_at"]):
        return _token_cache["token"]

    resp = httpx.post(
        os.environ["GATEWAY_TOKEN_ENDPOINT"],
        data={
            "grant_type":    "client_credentials",
            "client_id":     os.environ["GATEWAY_CLIENT_ID"],
            "client_secret": os.environ["GATEWAY_CLIENT_SECRET"],
            "scope":         os.environ["GATEWAY_SCOPE"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10.0,
    )
    resp.raise_for_status()
    body = resp.json()

    _token_cache["token"] = body["access_token"]
    _token_cache["expires_at"] = now + timedelta(
        seconds=body.get("expires_in", 3600) - 300
    )
    return _token_cache["token"]


def _build_mcp_client() -> MCPClient:
    gateway_url = os.environ["GATEWAY_MCP_URL"]

    def _open_stream():
        return streamablehttp_client(
            gateway_url,
            headers={"Authorization": f"Bearer {_fetch_bearer_token()}"},
        )

    return MCPClient(_open_stream)


# ── Agent setup ──────────────────────────────────────────────────────────
mcp_client = _build_mcp_client()

# Discover Lambda-backed tools from the Gateway at startup. The tool names
# and schemas come from the Gateway targets — the CLI-generated @tool stubs
# in main.py are not used on this path.
with mcp_client:
    gateway_tools = mcp_client.list_tools_sync()

    agent = Agent(
        model=BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-6",
            region_name="us-east-1",
        ),
        system_prompt=SYSTEM_PROMPT,
        tools=[current_time, *gateway_tools],
    )


app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload, context):
    # Each invocation refreshes the bearer token lazily through the cache.
    async for event in agent.stream_async(payload.get("prompt")):
        if "data" in event and isinstance(event["data"], str):
            yield event["data"]


if __name__ == "__main__":
    app.run()
