"""Call the LiteLLM gateway and report which configured deployment served it."""

from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Any

from openai import OpenAI

from reliable_inference import (
    MAX_OUTPUT_TOKENS,
    SYSTEM_PROMPT,
    GatewaySettings,
    load_gateway_settings,
    ticket_prompt,
)


@dataclass(frozen=True)
class GatewayProbe:
    text: str
    response_model: str
    deployment_id: str | None
    fallback_used: bool | None


def probe_gateway(
    ticket: str,
    order_context: str,
    *,
    settings: GatewaySettings | None = None,
    client: Any | None = None,
) -> GatewayProbe:
    gateway = settings or load_gateway_settings()
    openai_client = client or OpenAI(
        base_url=f"{gateway.base_url}/v1",
        api_key=gateway.api_key,
        max_retries=0,
        timeout=35,
    )
    raw_response = openai_client.chat.completions.with_raw_response.create(
        model=gateway.model_alias,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": ticket_prompt(ticket, order_context)},
        ],
        max_tokens=MAX_OUTPUT_TOKENS,
        temperature=0,
    )
    response = raw_response.parse()
    deployment_id = raw_response.headers.get("x-litellm-model-id")
    fallback_used = (
        None if deployment_id is None else deployment_id == "ticket-drafter-fallback"
    )
    return GatewayProbe(
        text=response.choices[0].message.content or "",
        response_model=response.model,
        deployment_id=deployment_id,
        fallback_used=fallback_used,
    )


def main() -> int:
    result = probe_gateway(
        "Where is order #10042?",
        "Order #10042 shipped on 4 August. Tracking ID ZX-1942.",
    )
    print(f"response_model={result.response_model}")
    print(f"deployment_id={result.deployment_id or 'header unavailable'}")
    print(
        "fallback_used="
        f"{result.fallback_used if result.fallback_used is not None else 'unknown'}"
    )
    print(result.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
