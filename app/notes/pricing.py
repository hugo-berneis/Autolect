"""Claude pricing (USD per 1M tokens) and per-call cost estimation.

Rates from the current Anthropic pricing (2026-11): cache writes ~1.25x input,
cache reads ~0.1x input.
"""
from __future__ import annotations

from .base import Usage

# (input_per_mtok, output_per_mtok)
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
}
_DEFAULT = (3.0, 15.0)


def estimate_cost(model: str, usage: Usage) -> float:
    in_rate, out_rate = PRICES.get(model, _DEFAULT)
    cost = (
        usage.input_tokens * in_rate
        + usage.cache_creation_input_tokens * in_rate * 1.25
        + usage.cache_read_input_tokens * in_rate * 0.1
        + usage.output_tokens * out_rate
    ) / 1_000_000
    return cost
