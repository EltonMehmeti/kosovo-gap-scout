"""Hand-rolled fakes for the Anthropic client and the budget guard (no network, no DB)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from scout.budget.guard import BudgetExceeded


@dataclass
class FakeUsage:
    input_tokens: int = 1000
    output_tokens: int = 100
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    server_tool_use: Any = None


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def tool_use_block(name: str, input: dict, id: str = "toolu_1") -> SimpleNamespace:  # noqa: A002
    return SimpleNamespace(type="tool_use", name=name, input=input, id=id)


@dataclass
class FakeMessage:
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: FakeUsage = field(default_factory=FakeUsage)
    parsed_output: Any = None
    _request_id: str | None = "req_fake"
    role: str = "assistant"


class FakeMessages:
    def __init__(self, responses) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses=()) -> None:
        self.messages = FakeMessages(responses)


class FakeGuard:
    """In-memory stand-in for BudgetGuard."""

    def __init__(self, cap: Decimal = Decimal("10"), day: date = date(2026, 10, 19)) -> None:
        self.cap = Decimal(cap)
        self.day = day
        self.run_id = None
        self.records: list = []

    def spent(self) -> Decimal:
        return sum((r.cost_eur for r in self.records), Decimal("0"))

    def remaining(self) -> Decimal:
        return max(Decimal("0"), self.cap - self.spent())

    def can_afford(self, est_eur) -> bool:
        return self.spent() + Decimal(est_eur) <= self.cap

    def check(self, est_eur) -> None:
        if self.spent() + Decimal(est_eur) > self.cap:
            raise BudgetExceeded(f"fake guard: spent {self.spent()} + {est_eur} > {self.cap}")

    def record(self, rec) -> Decimal:
        self.records.append(rec)
        return self.spent()
