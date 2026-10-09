"""Unit prices and cost arithmetic.

Prices are USD per million tokens as published for the Claude 5.5 family on
2026-10-09 (claude-api skill). Check platform.claude.com/pricing monthly; the
Costs page compares these estimates with the console bill.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

MTOK = Decimal(1_000_000)
SIX_DP = Decimal("0.000001")


@dataclass(frozen=True)
class ModelPrices:
    input_usd: Decimal
    output_usd: Decimal
    cache_write_usd: Decimal
    cache_read_usd: Decimal


MODEL_PRICES_USD_PER_MTOK: dict[str, ModelPrices] = {
    "claude-opus-5-5": ModelPrices(Decimal("4"), Decimal("20"), Decimal("5"), Decimal("0.20")),
    "claude-sonnet-5-5": ModelPrices(Decimal("2"), Decimal("10"), Decimal("2.5"), Decimal("0.20")),
    "claude-haiku-5-5": ModelPrices(
        Decimal("0.10"), Decimal("0.50"), Decimal("0.125"), Decimal("0.01")
    ),
}

WEB_SEARCH_USD_PER_CALL = Decimal("0.01")  # $10 per 1,000 searches

UNIT_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_write_tokens",
    "cache_read_tokens",
    "web_search_requests",
)


def usage_units(usage: object) -> dict[str, int]:
    """Flatten an SDK `usage` object into integer units, tolerating missing fields."""
    server = getattr(usage, "server_tool_use", None)
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "cache_write_tokens": int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
        "cache_read_tokens": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        "web_search_requests": int(getattr(server, "web_search_requests", 0) or 0),
    }


def llm_cost_usd(model: str, units: dict[str, int]) -> Decimal:
    p = MODEL_PRICES_USD_PER_MTOK[model]  # KeyError on unknown model is intentional
    g = units.get
    usd = (
        Decimal(g("input_tokens", 0)) * p.input_usd
        + Decimal(g("output_tokens", 0)) * p.output_usd
        + Decimal(g("cache_write_tokens", 0)) * p.cache_write_usd
        + Decimal(g("cache_read_tokens", 0)) * p.cache_read_usd
    ) / MTOK
    usd += Decimal(g("web_search_requests", 0)) * WEB_SEARCH_USD_PER_CALL
    return usd.quantize(SIX_DP, rounding=ROUND_HALF_UP)


def to_eur(usd: Decimal, usd_to_eur: Decimal) -> Decimal:
    return (usd * usd_to_eur).quantize(SIX_DP, rounding=ROUND_HALF_UP)
