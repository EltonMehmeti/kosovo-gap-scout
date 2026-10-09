"""Structured-output schemas for the Opus judgement calls. extra='forbid'; Literal enums; no constraints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

PresenceLevel = Literal[
    "absent",
    "exists-but-poor",
    "prishtina-only",
    "offline-only",
    "instagram-only",
    "decent",
    "unknown",
]
HardFilter = Literal[
    "none",
    "regulated-finance-health-gambling",
    "physical-inventory-or-fleet",
    "cardo-overlap",
    "test-cost-over-2000",
    "needs-full-time-before-revenue",
]
GapStatus = Literal["candidate", "verifying", "verified", "parked", "killed"]
CriticDecision = Literal["proceed", "needs_field_check", "park", "kill"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComponentScores(_Strict):
    proof: int
    absence: int
    demand: int
    founder_fit: int
    risk_penalty: int


class GapAssessment(_Strict):
    gap_id: int
    scores: ComponentScores
    presence_level: PresenceLevel
    confidence: float
    hard_filter_failed: HardFilter
    reasoning: str
    field_check_question: str
    recommended_status: GapStatus


class NewGapIdea(_Strict):
    title: str
    sector_slug: str
    hypothesis: str
    why_not_yet: str
    proven_model_slug: str


class StrategistOutput(_Strict):
    assessments: list[GapAssessment]
    new_gaps: list[NewGapIdea]
    headline: str


class CriticVerdict(_Strict):
    gap_id: int
    strongest_objection: str
    kosovo_killer: str
    risk_penalty: int
    confidence: float
    decision: CriticDecision
    field_check_question: str


class CriticOutput(_Strict):
    verdicts: list[CriticVerdict]


class DroppedTask(_Strict):
    task_id: int
    reason: str


class DirectorReview(_Strict):
    keep_task_ids_in_order: list[int]
    dropped: list[DroppedTask]
    note: str
