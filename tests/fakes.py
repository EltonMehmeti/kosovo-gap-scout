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

    def _next(self):
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._next()

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._next()


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


class FakeRunner:
    """Yields queued messages like the SDK runner; stops after a message without tool_use."""

    def __init__(self, messages, max_iterations=None) -> None:
        self._messages = list(messages)
        self._max = max_iterations
        self._count = 0
        self._last = None

    def __iter__(self):
        while self._messages and (self._max is None or self._count < self._max):
            self._last = self._messages.pop(0)
            self._count += 1
            yield self._last
            if not any(getattr(b, "type", "") == "tool_use" for b in self._last.content):
                return

    def generate_tool_call_response(self):
        if self._last is None:
            return None
        uses = [b for b in self._last.content if getattr(b, "type", "") == "tool_use"]
        if not uses:
            return None
        return {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": u.id, "content": "ok"} for u in uses
            ],
        }


def fake_runner_factory(script: list[list], calls: list[dict]):
    """Each runner construction pops the next list of messages from `script` and logs its kwargs."""

    def factory(**kwargs):
        calls.append(kwargs)
        return FakeRunner(script.pop(0), kwargs.get("max_iterations"))

    return factory
