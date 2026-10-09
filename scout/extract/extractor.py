"""Haiku-powered structured extraction (synchronous in M1; Message Batches in M3)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from scout.llm.gateway import LLM

EXTRACTOR_SYSTEM = (
    "You extract structured data from text for a market-research system about Kosovo. Output only what the "
    "text supports. When unsure, use 'other', 'unknown' or 'low' rather than guessing. Never invent names, "
    "numbers or URLs. Keep free-text fields to one sentence."
)
MAX_TEXT_CHARS = 300_000  # ≈ 75k tokens, under the 100k-token guidance for Haiku 5.5


class Extractor:
    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    def extract(
        self,
        output_format: type[BaseModel],
        instructions: str,
        text: str,
        *,
        model: str = "claude-haiku-5-5",
        effort: str = "low",
        est_eur: Decimal = Decimal("0.01"),
        max_tokens: int = 4096,
        task_id: int | None = None,
    ) -> BaseModel:
        user = f"{instructions.strip()}\n\n<text>\n{text[:MAX_TEXT_CHARS]}\n</text>"
        result = self.llm.parse(
            model=model,
            output_format=output_format,
            system=EXTRACTOR_SYSTEM,
            user=user,
            max_tokens=max_tokens,
            effort=effort,
            est_eur=est_eur,
            task_id=task_id,
        )
        return result.parsed
