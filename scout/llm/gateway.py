"""One door to the Anthropic API: budget check, call, cost record, stop-reason policing."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from scout.budget.pricing import llm_cost_usd, to_eur, usage_units
from scout.db.repo import CostRecord

SystemPrompt = str | list[dict[str, Any]]


class LLMError(RuntimeError):
    pass


class LLMRefusal(LLMError):
    pass


class LLMTruncated(LLMError):
    pass


@dataclass
class LLMResult:
    text: str
    parsed: Any | None
    stop_reason: str
    cost_eur: Decimal
    cache_read_tokens: int
    request_id: str | None


def message_text(message) -> str:
    parts = [
        b.text
        for b in (getattr(message, "content", None) or [])
        if getattr(b, "type", None) == "text"
    ]
    return "\n".join(parts).strip()


class LLM:
    def __init__(self, client, guard, usd_to_eur: Decimal) -> None:
        self.client = client
        self.guard = guard
        self.usd_to_eur = Decimal(usd_to_eur)

    def record_message(self, model: str, message, *, task_id: int | None = None) -> Decimal:
        units = usage_units(message.usage)
        eur = to_eur(llm_cost_usd(model, units), self.usd_to_eur)
        self.guard.record(
            CostRecord(
                "llm",
                "anthropic",
                model,
                units,
                eur,
                request_id=getattr(message, "_request_id", None),
                task_id=task_id,
            )
        )
        return eur

    def _finish(self, model: str, message, task_id: int | None) -> LLMResult:
        cost = self.record_message(model, message, task_id=task_id)
        units = usage_units(message.usage)
        result = LLMResult(
            text=message_text(message),
            parsed=getattr(message, "parsed_output", None),
            stop_reason=message.stop_reason,
            cost_eur=cost,
            cache_read_tokens=units["cache_read_tokens"],
            request_id=getattr(message, "_request_id", None),
        )
        if result.stop_reason == "refusal":
            raise LLMRefusal(f"{model} refused (request {result.request_id})")
        return result

    def create_text(
        self,
        *,
        model: str,
        system: SystemPrompt,
        user: str,
        max_tokens: int = 1024,
        effort: str = "medium",
        est_eur: Decimal,
        task_id: int | None = None,
    ) -> LLMResult:
        self.guard.check(est_eur)
        message = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort},
        )
        result = self._finish(model, message, task_id)
        if result.stop_reason == "max_tokens":
            raise LLMTruncated(f"{model} hit max_tokens={max_tokens} (request {result.request_id})")
        return result

    def parse(
        self,
        *,
        model: str,
        output_format: type,
        system: SystemPrompt,
        user: str,
        max_tokens: int = 4096,
        effort: str = "medium",
        est_eur: Decimal,
        task_id: int | None = None,
    ) -> LLMResult:
        self.guard.check(est_eur)
        message = self.client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=output_format,
            output_config={"effort": effort},
        )
        result = self._finish(model, message, task_id)
        if result.parsed is None:
            raise LLMTruncated(
                f"{model} returned no parsed output (stop_reason={result.stop_reason}, "
                f"request {result.request_id})"
            )
        return result
