# ruff: noqa: E501
"""Gap rubric (spec A3): 0–100, with caps that make hallucinated absence impossible to score high."""

from __future__ import annotations

from dataclasses import dataclass

PRESENCE_CAP: dict[str, int] = {
    "absent": 25,
    "exists-but-poor": 18,
    "prishtina-only": 12,
    "offline-only": 10,
    "decent": 0,
    "unknown": 12,
}
NO_CHECK_ABSENCE_CAP = 12
NO_CHECK_CONFIDENCE_CAP = 0.5
HARD_FILTERS = (
    "regulated-finance-health-gambling",
    "physical-inventory-or-fleet",
    "cardo-overlap",
    "test-cost-over-2000",
    "needs-full-time-before-revenue",
)

RUBRIC_TEXT = """Scoring rubric (0–100). You propose component scores; the system recomputes the total.
- proof (0–25): evidence the model works elsewhere. Count nearby markets (AL MK ME BA RS HR SI) three times,
  EU/US once; 25 means several nearby markets with traction evidence.
- absence (0–25): how missing it is in Kosovo. Cap by presence level: absent 25, exists-but-poor 18,
  prishtina-only 12, offline-only 10, decent 0, unknown 12. Without a presence check younger than 60 days
  the system caps absence at 12 and confidence at 0.5 regardless of what you propose.
- demand (0–20): signals Kosovars want it (complaints, searches, Instagram workarounds, diaspora pull,
  statistics on spend).
- founder_fit (0–15): software-only, buildable by one engineer in evenings, testable for ≤ €150 of ads,
  monetisable without a sales team, growable to Albanian speakers elsewhere.
- risk_penalty (0–15): the why-not-yet killer — payments, trust, informality, incumbents, regulation,
  logistics, market too small. The system awards 15 − penalty.
- hard filters (score 0, status killed): regulated finance/health/gambling; physical inventory or fleets;
  overlap with the founder's employer's asset-based-finance business; needs > €2,000 to test; needs the
  founder full-time before revenue. Name the filter in hard_filter_failed or use "none".
- confidence (0–1): how sure you are of the whole assessment, separate from the score."""


@dataclass(frozen=True)
class ScoreResult:
    total: int
    components: dict[str, int]
    confidence: float
    killed: bool
    reasons: list[str]


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def cap_confidence(confidence: float, has_presence_check: bool) -> float:
    c = max(0.0, min(1.0, float(confidence)))
    return min(c, NO_CHECK_CONFIDENCE_CAP) if not has_presence_check else c


def needs_field_check(total: int, confidence: float) -> bool:
    return total >= 60 and confidence < 0.6


def score_gap(
    *,
    proof: int,
    absence: int,
    demand: int,
    founder_fit: int,
    risk_penalty: int,
    presence_level: str,
    has_presence_check: bool,
    hard_filter_failed: str | None,
    confidence: float,
) -> ScoreResult:
    if hard_filter_failed not in (None, "none", ""):
        if hard_filter_failed not in HARD_FILTERS:
            raise ValueError(
                f"unknown hard filter {hard_filter_failed!r}; expected one of {HARD_FILTERS}"
            )
        return ScoreResult(
            total=0,
            components={"proof": 0, "absence": 0, "demand": 0, "founder_fit": 0, "risk": 0},
            confidence=cap_confidence(confidence, has_presence_check),
            killed=True,
            reasons=[f"hard filter: {hard_filter_failed}"],
        )
    reasons: list[str] = []
    absence_cap = PRESENCE_CAP.get(presence_level, PRESENCE_CAP["unknown"])
    if not has_presence_check:
        absence_cap = min(absence_cap, NO_CHECK_ABSENCE_CAP)
        reasons.append("no presence check ≤ 60 days: absence capped at 12, confidence at 0.5")
    components = {
        "proof": _clamp(proof, 0, 25),
        "absence": min(_clamp(absence, 0, 25), absence_cap),
        "demand": _clamp(demand, 0, 20),
        "founder_fit": _clamp(founder_fit, 0, 15),
        "risk": 15 - _clamp(risk_penalty, 0, 15),
    }
    return ScoreResult(
        total=sum(components.values()),
        components=components,
        confidence=cap_confidence(confidence, has_presence_check),
        killed=False,
        reasons=reasons,
    )
