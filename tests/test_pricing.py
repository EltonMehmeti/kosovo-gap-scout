from decimal import Decimal
from types import SimpleNamespace

import pytest

from scout.budget.pricing import llm_cost_usd, to_eur, usage_units


def test_usage_units_reads_sdk_usage_defensively():
    usage = SimpleNamespace(
        input_tokens=1000,
        output_tokens=200,
        cache_creation_input_tokens=300,
        cache_read_input_tokens=5000,
        server_tool_use=SimpleNamespace(web_search_requests=3),
    )
    assert usage_units(usage) == {
        "input_tokens": 1000,
        "output_tokens": 200,
        "cache_write_tokens": 300,
        "cache_read_tokens": 5000,
        "web_search_requests": 3,
    }


def test_usage_units_missing_fields_default_zero():
    usage = SimpleNamespace(input_tokens=10, output_tokens=5)
    units = usage_units(usage)
    assert units["cache_read_tokens"] == 0
    assert units["web_search_requests"] == 0


def test_sonnet_cost_arithmetic():
    units = {
        "input_tokens": 1_000_000,
        "output_tokens": 100_000,
        "cache_write_tokens": 0,
        "cache_read_tokens": 1_000_000,
        "web_search_requests": 10,
    }
    # 2.00 + 1.00 + 0.20 + 0.10
    assert llm_cost_usd("claude-sonnet-5-5", units) == Decimal("3.300000")


def test_haiku_and_opus_prices():
    units = {
        "input_tokens": 1_000_000,
        "output_tokens": 0,
        "cache_write_tokens": 0,
        "cache_read_tokens": 0,
        "web_search_requests": 0,
    }
    assert llm_cost_usd("claude-haiku-5-5", units) == Decimal("0.100000")
    assert llm_cost_usd("claude-opus-5-5", units) == Decimal("4.000000")


def test_unknown_model_raises():
    with pytest.raises(KeyError):
        llm_cost_usd("claude-unknown", {"input_tokens": 1})


def test_to_eur_quantises():
    assert to_eur(Decimal("1"), Decimal("0.92")) == Decimal("0.920000")
    assert to_eur(Decimal("0.0000001"), Decimal("0.92")) == Decimal("0.000000")
