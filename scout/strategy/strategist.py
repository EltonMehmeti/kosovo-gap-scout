"""Strategist (scores gaps) and Critic (attacks the top three); Python applies the rubric and writes state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from scout.budget.pricing import llm_cost_usd, to_eur
from scout.db import repo
from scout.db.models import GapAssessment as GapAssessmentRow
from scout.founder import founder_parked
from scout.llm.gateway import LLM
from scout.strategy import schemas as S
from scout.strategy.rubric import PRESENCE_CAP, RUBRIC_TEXT, needs_field_check, score_gap

MAX_FACTS_CHARS = 90_000  # ≈ 25k tokens
# C2: the Strategist judges only what changed, a bounded number of gaps, in a bounded prompt.
MAX_STRATEGY_GAPS = 15
MAX_DIGESTS = 8
DIGEST_CHARS = 3000
MAX_INPUT_CHARS = 150_000  # whole user payload, ≈ 40–50k tokens
OPUS = "claude-opus-5-5"
CRITIC_MAX_TOKENS = 8192
VERIFIED_CHECK_MAX_AGE_DAYS = 30
VERIFIED_MIN_CONFIDENCE = 0.7
VERIFIED_MIN_SCORE = 60  # the verifying threshold: a verified gap must at least be worth verifying
VERIFIED_MIN_CITATIONS = 2
VERIFIED_MIN_NEARBY_CITATIONS = 1

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


def strategist_max_tokens(n_gaps: int) -> int:
    """Thinking plus ≈ 200–400 output tokens per assessment, with headroom; never above 16k."""
    return min(16_000, 4_000 + 600 * max(1, n_gaps))


def changes_today(session, facts, touched_gap_ids) -> tuple[list[str], set[int]]:
    """Spec B2.4/B7 scope: sectors whose facts or gaps changed in this run, and the gaps touched.

    Sectors come from the fresh facts' sectors, the gaps those facts are about ("gap:<id>" keys) and the
    gaps the workers proposed or updated (ToolContext.touched_gap_ids)."""
    gap_ids = set(touched_gap_ids)
    for f in facts:
        key = f.entity_key or ""
        if key.startswith("gap:") and key[4:].isdigit():
            gap_ids.add(int(key[4:]))
    sector_ids = {f.sector_id for f in facts if f.sector_id}
    live: set[int] = set()
    for gid in gap_ids:
        gap = repo.get_gap(session, gid)
        if gap is not None:
            sector_ids.add(gap.sector_id)
            live.add(gid)
    slugs = {sec.id: sec.slug for sec in repo.list_sectors(session)}
    return sorted(slugs[i] for i in sector_ids if i in slugs), live


def check_verdict(fact) -> str:
    """The presence level recorded by the protocol run (the fact's `value["verdict"]`), never the model's
    restatement of it. Anything unrecognised reads as "unknown"."""
    verdict = (fact.value or {}).get("verdict") if isinstance(fact.value, dict) else None
    return verdict if verdict in PRESENCE_CAP else "unknown"


def verified_gate_failures(session, gap, v: S.CriticVerdict | None, score, *, now) -> list[str]:
    """Spec A10, enforced in Python from stored data. Empty list = the gap may become `verified`.

    - presence check ≤ 30 days old from a complete protocol run, with a verdict other than unknown;
    - ≥ 2 cited proof-elsewhere markets, ≥ 1 nearby (repo.proof_citations);
    - a payment_path fact keyed gap:<id>;
    - a Critic verdict for this gap in this run: `proceed`, or `needs_field_check` with the gap's field
      checks answered (≥ 1 answered, none open) — no verdict means no review, so no `verified`;
    - no open field check for the gap; confidence ≥ 0.7; score ≥ 60.
    """
    fails: list[str] = []
    check = repo.latest_presence_check(
        session, gap, now=now, max_age_days=VERIFIED_CHECK_MAX_AGE_DAYS
    )
    if check is None:
        fails.append(f"no presence check ≤ {VERIFIED_CHECK_MAX_AGE_DAYS} days")
    elif check_verdict(check) == "unknown":
        fails.append("presence verdict unknown")
    cited, nearby = repo.proof_citations(session, gap)
    if cited < VERIFIED_MIN_CITATIONS or nearby < VERIFIED_MIN_NEARBY_CITATIONS:
        fails.append(f"proof citations {cited} ({nearby} nearby)")
    if not repo.has_fact(session, entity_type="payment_path", entity_key=f"gap:{gap.id}", now=now):
        fails.append("no payment path")
    open_n, answered_n = repo.field_check_counts(session, gap.id)
    if open_n:
        fails.append("open field check")
    if v is None:
        fails.append("no critic review")
    elif v.decision == "needs_field_check" and answered_n == 0:
        fails.append("critic wants a field check")
    elif v.decision not in ("proceed", "needs_field_check"):
        fails.append(f"critic says {v.decision}")
    if score.confidence < VERIFIED_MIN_CONFIDENCE:
        fails.append(f"confidence {score.confidence:.2f}")
    if score.total < VERIFIED_MIN_SCORE:
        fails.append(f"score {score.total}")
    return fails


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
        self,
        *,
        since: datetime,
        now: datetime,
        sector_slugs: list[str] | None = None,
        priority_gap_ids=(),
    ) -> StrategyInputs:
        """Gaps in `sector_slugs` (all when None), capped at MAX_STRATEGY_GAPS: touched today first, then
        never scored, then the stalest `last_assessed_run_id`, so every gap rotates through. Facts are the
        fresh ones in those sectors or about the chosen gaps; the whole payload stays ≤ MAX_INPUT_CHARS."""
        s = self.session
        sectors = {sec.id: sec.slug for sec in repo.list_sectors(s)}
        priority = set(priority_gap_ids)
        candidates = repo.list_gaps(
            s, statuses=["candidate", "verifying", "verified", "parked"], sector_slugs=sector_slugs
        )
        held = set(founder_parked(s))  # the founder parked these: leave them alone
        candidates = [g for g in candidates if g.id not in held]
        candidates.sort(
            key=lambda g: (
                g.id not in priority,
                g.score_components is not None,
                g.last_assessed_run_id is not None,
                g.last_assessed_run_id or 0,
                g.id,
            )
        )
        chosen = sorted(candidates[:MAX_STRATEGY_GAPS], key=lambda g: g.id)
        gaps = []
        for g in chosen:
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
        wanted = list(dict.fromkeys([*sorted(sector_slugs or []), *(g["sector"] for g in gaps)]))
        digests = {
            slug: (repo.get_digest(s, f"sector:{slug}") or "")[:DIGEST_CHARS]
            for slug in [w for w in wanted if w][:MAX_DIGESTS]
        }
        if sector_slugs is None:
            facts_rows = repo.fresh_facts_since(s, since, now=now)
        else:
            facts_rows = repo.fresh_facts_for(
                s,
                since,
                now=now,
                sector_ids={i for i, slug in sectors.items() if slug in set(sector_slugs)},
                entity_keys={f"gap:{g.id}" for g in chosen},
            )
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
        inputs = StrategyInputs(
            country_md=(repo.get_digest(s, "country") or "")[:DIGEST_CHARS],
            sector_digests=digests,
            facts=[],
            gaps=gaps,
            taxonomy=sorted(sectors.values()),
        )
        room = min(MAX_FACTS_CHARS, MAX_INPUT_CHARS - len(self.payload(inputs, now.date())))
        used = 0
        for f in facts:  # a list item costs its JSON plus ", " — an exact upper bound
            used += len(json.dumps(f, ensure_ascii=False)) + 2
            if used > room:
                break
            inputs.facts.append(f)
        return inputs

    @staticmethod
    def payload(inputs: StrategyInputs, today: date) -> str:
        return json.dumps(
            {
                "date": today.isoformat(),
                "country_digest": inputs.country_md,
                "sector_digests": inputs.sector_digests,
                "facts": inputs.facts,
                "gaps": inputs.gaps,
                "sector_taxonomy": inputs.taxonomy,
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    def _est_eur(self, user: str, max_tokens: int) -> Decimal:
        """Worst case for one Opus call: the whole prompt (≈ 3 chars/token + system) and a full answer."""
        units = {"input_tokens": len(user) // 3 + 3_000, "output_tokens": max_tokens}
        return max(Decimal("0.10"), to_eur(llm_cost_usd(OPUS, units), self.llm.usd_to_eur))

    def assess(self, inputs: StrategyInputs, today: date) -> S.StrategistOutput:
        user = self.payload(inputs, today)
        max_tokens = strategist_max_tokens(len(inputs.gaps))
        res = self.llm.parse(
            model=OPUS,
            output_format=S.StrategistOutput,
            system=_system(STRATEGIST_SYSTEM),
            user=user,
            max_tokens=max_tokens,
            effort="medium",
            est_eur=self._est_eur(user, max_tokens),
        )
        return res.parsed

    def critique(
        self, output: S.StrategistOutput, inputs: StrategyInputs, today: date, top_n: int = 3
    ) -> S.CriticOutput:
        known = {g["id"]: g for g in inputs.gaps}

        def capped_total(a: S.GapAssessment) -> int:
            """The total the rubric will actually give (presence caps applied), not the raw sum."""
            g = known.get(a.gap_id, {})
            return score_gap(
                proof=a.scores.proof,
                absence=a.scores.absence,
                demand=a.scores.demand,
                founder_fit=a.scores.founder_fit,
                risk_penalty=a.scores.risk_penalty,
                presence_level=g.get("presence_check_verdict")
                or g.get("presence_level")
                or "unknown",
                has_presence_check=bool(g.get("has_presence_check")),
                hard_filter_failed=None if a.hard_filter_failed == "none" else a.hard_filter_failed,
                confidence=a.confidence,
            ).total

        ranked = sorted(output.assessments, key=lambda a: (-capped_total(a), a.gap_id))
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
        user = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        res = self.llm.parse(
            model=OPUS,
            output_format=S.CriticOutput,
            system=_system(CRITIC_SYSTEM),
            user=user,
            max_tokens=CRITIC_MAX_TOKENS,
            effort="high",
            est_eur=self._est_eur(user, CRITIC_MAX_TOKENS),
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
        critic_ok: bool = True,
    ) -> ApplyResult:
        """Write scores and statuses. `critic_ok=False` (the Critic call failed) applies the Strategist's
        output unreviewed: a gap that already had a score cannot gain score or confidence, and no gap can
        become verified (no Critic verdict)."""
        s = self.session
        result = ApplyResult()
        verdicts = {v.gap_id: v for v in critic.verdicts}
        held = set(founder_parked(s))
        open_checks = len(repo.open_field_checks(s))
        for a in output.assessments:
            gap = repo.get_gap(s, a.gap_id)
            if gap is None or gap.status == "killed" or gap.id in held:
                continue
            v = verdicts.get(a.gap_id)
            risk_penalty = (
                max(a.scores.risk_penalty, v.risk_penalty) if v else a.scores.risk_penalty
            )
            confidence = min(a.confidence, v.confidence) if v else a.confidence
            check = repo.latest_presence_check(s, gap, now=now, max_age_days=60)
            has_check_60 = check is not None
            check_30 = repo.latest_presence_check(
                s, gap, now=now, max_age_days=VERIFIED_CHECK_MAX_AGE_DAYS
            )
            check_30_ok = check_30 is not None and check_verdict(check_30) != "unknown"
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
            if not critic_ok and gap.score_components is not None:
                # unreviewed: a previously scored gap may fall but never rise
                if score.total > (gap.score_total or 0):
                    score = replace(
                        score, total=gap.score_total or 0, components=dict(gap.score_components)
                    )
                score = replace(score, confidence=min(score.confidence, gap.confidence or 0.0))
            old_status, old_score = gap.status, gap.score_total
            blocked: list[str] = []
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
            elif (
                old_status == "verified"
                and check_30_ok
                and score.confidence >= VERIFIED_MIN_CONFIDENCE
            ):
                # verified is demoted only by a Critic park/kill, an expired check or confidence < 0.7
                new_status = "verified"
            elif a.recommended_status == "killed":
                new_status, flag = "parked", "strategist-says-kill"
            elif a.recommended_status == "parked":
                new_status = "parked"
            elif a.recommended_status == "verified" and not (
                blocked := verified_gate_failures(s, gap, v, score, now=now)
            ):
                new_status = "verified"
            elif score.total >= 60:
                new_status = "verifying"
            else:
                new_status = "candidate"
            wants_check = (v and v.decision == "needs_field_check") or needs_field_check(
                score.total, score.confidence
            )
            if (
                wants_check
                and question
                and new_status != "verified"
                and open_checks < max_open_field_checks
            ):
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
                    model=OPUS,
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
                        (a.reasoning or "")[:200]
                        + (f" (not verified: {'; '.join(blocked)})" if blocked else ""),
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
