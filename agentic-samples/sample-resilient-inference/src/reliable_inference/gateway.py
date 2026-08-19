from __future__ import annotations

from dataclasses import dataclass
from functools import cache
import os
import time

import boto3
from strands import Agent
from strands.models import LiteLLMModel

from .core import Draft, MAX_OUTPUT_TOKENS, SYSTEM_PROMPT, ticket_prompt


@dataclass(frozen=True)
class GatewaySettings:
    base_url: str
    api_key: str
    model_alias: str = "ticket-drafter"


@cache
def _secrets_client():
    return boto3.client("secretsmanager")


def _load_gateway_api_key() -> str:
    if api_key := os.getenv("LITELLM_API_KEY"):
        return api_key

    secret_id = os.getenv("LITELLM_API_KEY_SECRET_ID")
    if not secret_id:
        raise RuntimeError(
            "set LITELLM_API_KEY locally or LITELLM_API_KEY_SECRET_ID in Runtime"
        )

    secret = _secrets_client().get_secret_value(SecretId=secret_id).get("SecretString")
    if not isinstance(secret, str) or not secret:
        raise RuntimeError(f"secret {secret_id!r} has no SecretString")
    return secret


def load_gateway_settings() -> GatewaySettings:
    return GatewaySettings(
        base_url=os.getenv("LITELLM_BASE_URL", "http://localhost:4000").rstrip("/"),
        api_key=_load_gateway_api_key(),
        model_alias=os.getenv("LITELLM_MODEL_ALIAS", "ticket-drafter"),
    )


def build_gateway_ticket_agent(
    settings: GatewaySettings | None = None,
    *,
    max_tokens: int = MAX_OUTPUT_TOKENS,
) -> Agent:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    gateway = settings or load_gateway_settings()
    model = LiteLLMModel(
        client_args={
            "api_base": gateway.base_url,
            "api_key": gateway.api_key,
            "use_litellm_proxy": True,
            "num_retries": 0,
            "timeout": 35,
        },
        model_id=gateway.model_alias,
        params={"max_tokens": max_tokens, "temperature": 0},
        stream=False,
    )
    return Agent(model=model, system_prompt=SYSTEM_PROMPT)


def draft_reply_via_gateway(
    ticket: str,
    order_context: str,
    *,
    settings: GatewaySettings | None = None,
    max_tokens: int = MAX_OUTPUT_TOKENS,
) -> Draft:
    if not ticket.strip():
        raise ValueError("ticket must not be empty")

    gateway = settings or load_gateway_settings()
    agent = build_gateway_ticket_agent(gateway, max_tokens=max_tokens)
    started = time.perf_counter()
    result = agent(ticket_prompt(ticket, order_context))
    latency_ms = round((time.perf_counter() - started) * 1_000)

    text = str(result).strip()
    if not text:
        raise RuntimeError("The ticket agent returned no text content")

    usage = result.metrics.get_summary()["accumulated_usage"]
    return Draft(
        text=text,
        model_id=gateway.model_alias,
        latency_ms=latency_ms,
        input_tokens=usage["inputTokens"],
        output_tokens=usage["outputTokens"],
        stop_reason=result.stop_reason,
    )
