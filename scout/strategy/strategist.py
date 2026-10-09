"""Strategist (scores gaps) and Critic (attacks the top three); Python applies the rubric and writes state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from scout.db import repo
from scout.db.models import GapAssessment as GapAssessmentRow
from scout.llm.gateway import LLM
from scout.strategy import schemas as S
from scout.strategy.rubric import PRESENCE_CAP, RUBRIC_TEXT, needs_field_check, score_gap

MAX_FACTS_CHARS = 90_000  # ≈ 25k tokens
VERIFIED_CHECK_MAX_AGE_DAYS = 30
VERIFIED_MIN_CONFIDENCE = 0.7

STRATEGIST_SYSTEM = """You are the Strategist of Kosovo Gap Scout. Once a day you read what the research workers
learned and judge each tracked gap: a consumer business model proven elsewhere that may be missing in Kosovo,
to be started by a solo software engineer in Prishtina with 5–10 hours a week and ≤ €2,000.

Rules:
- Score only from the facts and digests given; cite them in `reasoning`. If the evidence is thin, lower
  `confidence` instead of guessing scores.
- Presence level must come from a presence_check fact; otherwise keep the gap's current level or "unknown".
- Recommend "verified" only when a presence check exists, proof has at least two sources with one nearby
  market, a payment path is recorded and your confidence is ≥ 0.7. Recommend "killed" only through a hard
  filter — otherwise "parked".
- A field check is a question the founder can answer in three minutes by phone or by walking into a shop in
  Prishtina, Prizren, Pejë, Gjakovë, Mitrovicë, Ferizaj or Gjilan. Propose one only when it would change the
  score or the confidence materially.
- Propose new gaps only when the facts show a proven model with no sign of a Kosovo equivalent; one line of
  hypothesis each, sector slug from the taxonomy in the input.
- Be concrete and short. Reasoning ≤ 80 words per gap.
"""

CRITIC_SYSTEM = """You are the Critic of Kosovo Gap Scout. You see the Strategist's top gaps and the same facts.
Your job is to find what would make a careful Kosovar operator say "this will not work here": the payment
path (cash culture, no PayPal payouts, card fees), trust (people buy from people they know), informality
(a WhatsApp group already does it for free), logistics, a hidden incumbent (a Telegram/Instagram seller,
a bank's app, Gjirafa, Wolt, a telecom), regulation, or a market too small for the model's economics.
For each gap give the strongest objection, the Kosovo-specific killer, your own risk_penalty (0–15) and
confidence (0–1), and a decision: proceed, needs_field_check (with the question), park or kill.
Decide "kill" only if the objection is close to certain; otherwise "park" or "needs_field_check".
"""


@dataclass
class StrategyInputs:
    country_md: str
    sector_digests: dict[str, str]
    facts: list[dict]
    gaps: list[dict]
    taxonomy: list[str] = field(default_factory=list)


@dataclass
class GapChange:
    gap_id: int
    title: str
    old_status: str
    new_status: str
    old_score: int
    new_score: int
    confidence: float
    why: str


@dataclass
class ApplyResult:
    changes: list[GapChange] = field(default_factory=list)
    field_checks_added: int = 0
    new_gaps: int = 0


def check_verdict(fact) -> str:
    """The presence level recorded by the protocol run (the fact's `value["verdict"]`), never the model's
    restatement of it. Anything unrecognised reads as "unknown"."""
    verdict = (fact.value or {}).get("verdict") if isinstance(fact.value, dict) else None
    return verdict if verdict in PRESENCE_CAP else "unknown"


def _system(text: str) -> list[dict]:
    return [
        {"type": "text", "text": text},
        {"type": "text", "text": RUBRIC_TEXT, "cache_control": {"type": "ephemeral"}},
    ]


class Strategist:
    def __init__(self, llm: LLM, session) -> None:
        self.llm = llm
        self.session = session

    def collect_inputs(
        self, *, since: datetime, now: datetime, sector_slugs: list[str] | None = None
    ) -> StrategyInputs:
        s = self.session
        facts_rows = repo.fresh_facts_since(s, since, sector_slugs=sector_slugs, now=now)
        facts = sorted(
            (
                {
                    "claim": f.claim,
                    "confidence": f.confidence,
                    "type": f.entity_type,
                    "key": f.entity_key,
                    "source": f.source_url or f.source_name,
                    "observed": f.observed_at.date().isoformat(),
                }
                for f in facts_rows
            ),
            key=lambda d: (-d["confidence"], d["claim"]),
        )
        while len(json.dumps(facts, ensure_ascii=False)) > MAX_FACTS_CHARS and facts:
            facts.pop()
        gaps = []
        sectors = {sec.id: sec.slug for sec in repo.list_sectors(s)}
        for g in repo.list_gaps(
            s, statuses=["candidate", "verifying", "verified", "parked"], sector_slugs=sector_slugs
        ):
            check = repo.latest_presence_check(s, g, now=now)
            gaps.append(
                {
                    "id": g.id,
                    "title": g.title,
                    "sector": sectors.get(g.sector_id),
                    "status": g.status,
                    "score": g.score_total,
                    "confidence": g.confidence,
                    "presence_level": g.presence_level,
                    "has_presence_check": check is not None,
                    "presence_check_verdict": check_verdict(check) if check else None,
                    "hypothesis": g.hypothesis_md[:600],
                    "why_not_yet": g.why_not_yet_md[:400],
                    "components": g.score_components or {},
                }
            )
        gaps.sort(key=lambda d: d["id"])
        wanted = {g["sector"] for g in gaps} | set(sector_slugs or [])
        digests = {
            slug: (repo.get_digest(s, f"sector:{slug}") or "")[:3000]
            for slug in sorted(wanted)
            if slug
        }
        return StrategyInputs(
            country_md=(repo.get_digest(s, "country") or "")[:3000],
            sector_digests=digests,
            facts=facts,
            gaps=gaps,
            taxonomy=sorted(sectors.values()),
        )

    def assess(self, inputs: StrategyInputs, today: date) -> S.StrategistOutput:
        payload = {
            "date": today.isoformat(),
            "country_digest": inputs.country_md,
            "sector_digests": inputs.sector_digests,
            "facts": inputs.facts,
            "gaps": inputs.gaps,
            "sector_taxonomy": inputs.taxonomy,
        }
        res = self.llm.parse(
            model="claude-opus-5-5",
            output_format=S.StrategistOutput,
            system=_system(STRATEGIST_SYSTEM),
            user=json.dumps(payload, sort_keys=True, ensure_ascii=False),
            max_tokens=8192,
            effort="medium",
            est_eur=Decimal("0.40"),
        )
        return res.parsed

    def critique(
        self, output: S.StrategistOutput, inputs: StrategyInputs, today: date, top_n: int = 3
    ) -> S.CriticOutput:
        ranked = sorted(
            output.assessments,
            key=lambda a: (
                -(
                    a.scores.proof
                    + a.scores.absence
                    + a.scores.demand
                    + a.scores.founder_fit
                    - a.scores.risk_penalty
                )
            ),
        )
        top = ranked[:top_n]
        if not top:
            return S.CriticOutput(verdicts=[])
        ids = {a.gap_id for a in top}
        payload = {
            "date": today.isoformat(),
            "assessments": [a.model_dump() for a in top],
            "gaps": [g for g in inputs.gaps if g["id"] in ids],
            "facts": inputs.facts,
            "country_digest": inputs.country_md,
        }
        res = self.llm.parse(
            model="claude-opus-5-5",
            output_format=S.CriticOutput,
            system=_system(CRITIC_SYSTEM),
            user=json.dumps(payload, sort_keys=True, ensure_ascii=False),
            max_tokens=4096,
            effort="high",
            est_eur=Decimal("0.30"),
        )
        return res.parsed

    def apply(
        self,
        output: S.StrategistOutput,
        critic: S.CriticOutput,
        *,
        now: datetime,
        run_id: int | None,
        max_open_field_checks: int = 5,
    ) -> ApplyResult:
        s = self.session
        result = ApplyResult()
        verdicts = {v.gap_id: v for v in critic.verdicts}
        open_checks = len(repo.open_field_checks(s))
        for a in output.assessments:
            gap = repo.get_gap(s, a.gap_id)
            if gap is None or gap.status == "killed":
                continue
            v = verdicts.get(a.gap_id)
            risk_penalty = (
                max(a.scores.risk_penalty, v.risk_penalty) if v else a.scores.risk_penalty
            )
            confidence = min(a.confidence, v.confidence) if v else a.confidence
            check = repo.latest_presence_check(s, gap, now=now, max_age_days=60)
            has_check_60 = check is not None
            has_check_30 = repo.has_presence_check(
                s, gap, now=now, max_age_days=VERIFIED_CHECK_MAX_AGE_DAYS
            )
            presence = check_verdict(check) if check else (gap.presence_level or "unknown")
            score = score_gap(
                proof=a.scores.proof,
                absence=a.scores.absence,
                demand=a.scores.demand,
                founder_fit=a.scores.founder_fit,
                risk_penalty=risk_penalty,
                presence_level=presence,
                has_presence_check=has_check_60,
                hard_filter_failed=None if a.hard_filter_failed == "none" else a.hard_filter_failed,
                confidence=confidence,
            )
            old_status, old_score = gap.status, gap.score_total
            question = (
                v.field_check_question if v and v.field_check_question else a.field_check_question
            ).strip()
            new_status, flag = old_status, gap.critic_flag
            if score.killed:
                new_status = "killed"
            elif v and v.decision == "kill":
                new_status, flag = "parked", "critic-says-kill"
            elif v and v.decision == "park":
                new_status = "parked"
            elif a.recommended_status == "killed":
                new_status, flag = "parked", "strategist-says-kill"
            elif a.recommended_status == "parked":
                new_status = "parked"
            elif (
                a.recommended_status == "verified"
                and has_check_30
                and score.confidence >= VERIFIED_MIN_CONFIDENCE
                and not (v and v.decision == "needs_field_check")
            ):
                new_status = "verified"
            elif score.total >= 60:
                new_status = "verifying"
            else:
                new_status = "candidate"
            wants_check = (v and v.decision == "needs_field_check") or needs_field_check(
                score.total, score.confidence
            )
            if wants_check and question and open_checks < max_open_field_checks:
                repo.add_field_check(
                    s,
                    gap_id=gap.id,
                    question=question,
                    why=f"score {score.total}, confidence {score.confidence:.2f}",
                    due=(now + timedelta(days=7)).date(),
                )
                open_checks += 1
                result.field_checks_added += 1
            gap.presence_level = presence
            gap.score_total = score.total
            gap.score_components = score.components
            gap.confidence = score.confidence
            gap.status = new_status
            gap.critic_flag = flag
            gap.updated_at = now
            gap.last_assessed_run_id = run_id
            s.add(
                GapAssessmentRow(
                    gap_id=gap.id,
                    run_id=run_id,
                    model="claude-opus-5-5",
                    strategist=a.model_dump(),
                    critic=v.model_dump() if v else None,
                    score_total=score.total,
                    confidence=score.confidence,
                )
            )
            s.commit()
            if new_status != old_status or score.total != old_score:
                result.changes.append(
                    GapChange(
                        gap.id,
                        gap.title,
                        old_status,
                        new_status,
                        old_score,
                        score.total,
                        score.confidence,
                        (a.reasoning or "")[:200],
                    )
                )
        for idea in output.new_gaps:
            if repo.get_sector(s, idea.sector_slug) is None:
                continue
            _, created = repo.propose_gap(
                s,
                title=idea.title,
                sector_slug=idea.sector_slug,
                proven_model_slug=idea.proven_model_slug or None,
                hypothesis_md=idea.hypothesis,
                why_not_yet_md=idea.why_not_yet,
                run_id=run_id,
            )
            result.new_gaps += int(created)
        return result
