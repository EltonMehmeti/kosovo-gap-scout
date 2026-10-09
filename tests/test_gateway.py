from decimal import Decimal
from types import SimpleNamespace

import pytest

from scout.budget.guard import BudgetExceeded
from scout.llm.gateway import LLM, LLMRefusal, LLMTruncated, message_text
from tests.fakes import FakeClient, FakeGuard, FakeMessage, FakeUsage, text_block


def test_parse_records_cost_and_returns_parsed():
    guard = FakeGuard()
    msg = FakeMessage(
        content=[text_block('{"a": 1}')],
        parsed_output={"a": 1},
        usage=FakeUsage(input_tokens=1_000_000, output_tokens=0),
    )
    llm = LLM(FakeClient([msg]), guard, Decimal("0.92"))
    res = llm.parse(
        model="claude-haiku-5-5",
        output_format=dict,
        system="s",
        user="u",
        est_eur=Decimal("0.01"),
    )
    assert res.parsed == {"a": 1}
    assert res.cost_eur == Decimal("0.092000")  # $0.10 * 0.92
    rec = guard.records[0]
    assert rec.model == "claude-haiku-5-5" and rec.request_id == "req_fake" and rec.kind == "llm"
    call = llm.client.messages.calls[0]
    assert call["output_config"] == {"effort": "medium"}
    assert call["output_format"] is dict
    assert "thinking" not in call and "tool_choice" not in call


def test_check_happens_before_the_call():
    guard = FakeGuard(cap=Decimal("0.005"))
    client = FakeClient([FakeMessage()])
    llm = LLM(client, guard, Decimal("0.92"))
    with pytest.raises(BudgetExceeded):
        llm.parse(
            model="claude-haiku-5-5",
            output_format=dict,
            system="s",
            user="u",
            est_eur=Decimal("0.01"),
        )
    assert client.messages.calls == []


def test_refusal_and_truncation_raise_but_still_record_cost():
    guard = FakeGuard()
    refusal = FakeMessage(content=[], stop_reason="refusal")
    truncated = FakeMessage(content=[text_block("partial")], stop_reason="max_tokens")
    no_parse = FakeMessage(content=[text_block("{")], stop_reason="max_tokens", parsed_output=None)
    llm = LLM(FakeClient([refusal, truncated, no_parse]), guard, Decimal("0.92"))
    with pytest.raises(LLMRefusal):
        llm.create_text(model="claude-sonnet-5-5", system="s", user="u", est_eur=Decimal("0.01"))
    with pytest.raises(LLMTruncated):
        llm.create_text(model="claude-sonnet-5-5", system="s", user="u", est_eur=Decimal("0.01"))
    with pytest.raises(LLMTruncated):
        llm.parse(
            model="claude-haiku-5-5",
            output_format=dict,
            system="s",
            user="u",
            est_eur=Decimal("0.01"),
        )
    assert len(guard.records) == 3


def test_message_text_joins_text_blocks_only():
    msg = FakeMessage(content=[text_block("a"), SimpleNamespace(type="tool_use"), text_block("b")])
    assert message_text(msg) == "a\nb"
    llm = LLM(FakeClient([msg]), FakeGuard(), Decimal("0.92"))
    res = llm.create_text(
        model="claude-sonnet-5-5",
        system=[{"type": "text", "text": "s"}],
        user="u",
        est_eur=Decimal("0"),
    )
    assert res.text == "a\nb" and res.cache_read_tokens == 0
