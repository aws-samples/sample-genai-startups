from __future__ import annotations

from decimal import Decimal

from jev_semanticlayer.config import Settings
from jev_semanticlayer.schema import Usage


MILLION = Decimal("1000000")


def _token_cost(tokens: int, usd_per_million: Decimal) -> Decimal:
    return Decimal(tokens) * usd_per_million / MILLION


def calculate_usage(
    settings: Settings,
    *,
    frontier_input_tokens: int = 0,
    frontier_output_tokens: int = 0,
    jev_input_tokens: int = 0,
    jev_output_tokens: int = 0,
) -> Usage:
    frontier = _token_cost(
        frontier_input_tokens, settings.bedrock_input_usd_per_million
    ) + _token_cost(
        frontier_output_tokens, settings.bedrock_output_usd_per_million
    )
    jev = _token_cost(
        jev_input_tokens, settings.jev_input_usd_per_million
    ) + _token_cost(
        jev_output_tokens, settings.jev_output_usd_per_million
    )
    return Usage(
        frontier_input_tokens=frontier_input_tokens,
        frontier_output_tokens=frontier_output_tokens,
        jev_input_tokens=jev_input_tokens,
        jev_output_tokens=jev_output_tokens,
        frontier_cost_usd=float(frontier),
        jev_cost_usd=float(jev),
        total_cost_usd=float(frontier + jev),
    )

