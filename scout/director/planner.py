"""Deterministic daily planner (spec B9). Pure function over a snapshot of the knowledge base."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from scout.db import repo
from scout.worker.profiles import PROFILES

PHASES = ("foundation", "verification", "maintenance")
PHASE_RULES: dict[str, dict] = {
    "foundation": {
        "cap": Decimal("3.00"),
        "map-sector": 2,
        "hunt-models": 2,
        "verify-gap": 1,
        "culture": 1,
    },
    "verification": {
        "cap": Decimal("1.50"),
        "map-sector": 0,
        "hunt-models": 0,
        "verify-gap": 2,
        "culture": 0,
    },
    "maintenance": {
        "cap": Decimal("0.80"),
        "map-sector": 0,
        "hunt-models": 0,
        "verify-gap": 0,
        "culture": 0,
    },
}
MAP_STALE_DAYS = 14
HUNT_STALE_DAYS = 21
CHART_DIFF_EST = Decimal("0.05")
MAX_OPEN_FIELD_CHECKS = 5
PRIORITY = {
    "verify-gap": 85,
    "map-sector": 80,
    "hunt-models": 75,
    "chart-diff": 70,
    "news-scan": 60,
    "culture": 55,
    "deep-dive": 40,
}


@dataclass
class SectorInfo:
    slug: str
    name_en: str
    priority: int
    status: str
    last_mapped_at: datetime | None
    last_hunted_at: datetime | None


@dataclass
class GapInfo:
    id: int
    title: str
    sector_slug: str
    score_total: int
    confidence: float
    status: str
    has_fresh_check: bool


@dataclass
class PlannerState:
    today: date
    sectors: list[SectorInfo]
    culture_themes_missing: list[str]
    gaps: list[GapInfo]
    open_field_checks: int
    spent_today: Decimal
    cap: Decimal
    flagged_gap_ids: list[int] = field(default_factory=list)
    deep_dive_done_this_month: bool = False
    done_today: set[tuple[str, str]] = field(default_factory=set)


@dataclass
class PlannedTask:
    profile: str
    payload: dict
    priority: int
    est_cost_eur: Decimal


def _key(profile: str, payload: dict) -> tuple[str, str]:
    return profile, str(
        payload.get("gap_id") or payload.get("sector") or payload.get("theme") or ""
    )


def _gap_payload(g: GapInfo) -> dict:
    return {"gap_id": g.id, "gap_title": g.title, "sector": g.sector_slug}


def _verify_candidates(state: PlannerState) -> list[GapInfo]:
    live = [g for g in state.gaps if g.status in ("candidate", "verifying", "verified")]
    flagged = [g for g in live if g.id in state.flagged_gap_ids]
    needs = [
        g
        for g in live
        if g.id not in state.flagged_gap_ids and (not g.has_fresh_check or g.confidence < 0.6)
    ]
    if state.open_field_checks >= MAX_OPEN_FIELD_CHECKS:
        # the founder has enough homework: prefer gaps whose check is already done
        needs.sort(key=lambda g: (not g.has_fresh_check, -g.score_total, -g.confidence))
    else:
        needs.sort(key=lambda g: (g.has_fresh_check, -g.score_total, g.confidence))
    return flagged + needs


def plan_tasks(state: PlannerState, phase: str) -> list[PlannedTask]:
    rules = PHASE_RULES[phase]
    if state.spent_today >= state.cap:
        return []
    weekday = state.today.weekday()  # Monday = 0, Sunday = 6
    wanted: list[PlannedTask] = []

    def add(
        profile: str, payload: dict, priority: int | None = None, est: Decimal | None = None
    ) -> None:
        if _key(profile, payload) in state.done_today or any(
            _key(t.profile, t.payload) == _key(profile, payload) for t in wanted
        ):
            return
        est = est if est is not None else PROFILES[profile].est_cost_eur
        wanted.append(
            PlannedTask(
                profile, payload, priority if priority is not None else PRIORITY[profile], est
            )
        )

    # verify-gap
    n_verify = rules["verify-gap"]
    for g in _verify_candidates(state):
        is_flagged = g.id in state.flagged_gap_ids
        if phase == "maintenance" and not is_flagged:
            continue
        if not is_flagged and n_verify <= 0:
            continue
        add("verify-gap", _gap_payload(g), 90 if is_flagged else None)
        if not is_flagged:
            n_verify -= 1
    # map-sector: unmapped by priority, then stale
    unmapped = sorted(
        (s for s in state.sectors if s.status == "unmapped"), key=lambda s: (s.priority, s.slug)
    )
    stale_cut = datetime.combine(state.today, datetime.min.time(), tzinfo=None) - timedelta(
        days=MAP_STALE_DAYS
    )
    stale = sorted(
        (
            s
            for s in state.sectors
            if s.status != "unmapped"
            and s.last_mapped_at is not None
            and s.last_mapped_at.replace(tzinfo=None) < stale_cut
        ),
        key=lambda s: s.last_mapped_at,
    )
    mapped_today: list[str] = []
    for s in (unmapped + stale)[: rules["map-sector"] + len(state.done_today)]:
        if sum(1 for t in wanted if t.profile == "map-sector") >= rules["map-sector"]:
            break
        before = len(wanted)
        add("map-sector", {"sector": s.slug, "sector_name": s.name_en})
        if len(wanted) > before:
            mapped_today.append(s.slug)
    # hunt-models: mapped sectors never hunted or hunted long ago, not mapped today
    hunt_cut = stale_cut + timedelta(days=MAP_STALE_DAYS - HUNT_STALE_DAYS)
    huntable = [
        s
        for s in state.sectors
        if s.status != "unmapped"
        and s.slug not in mapped_today
        and (s.last_hunted_at is None or s.last_hunted_at.replace(tzinfo=None) < hunt_cut)
    ]
    huntable.sort(key=lambda s: (s.last_hunted_at is not None, s.priority, s.slug))
    for s in huntable:
        if sum(1 for t in wanted if t.profile == "hunt-models") >= rules["hunt-models"]:
            break
        add("hunt-models", {"sector": s.slug, "sector_name": s.name_en})
    # weekly and daily fixtures
    if weekday == 0:
        add("chart-diff", {}, est=CHART_DIFF_EST)
    add("news-scan", {})
    if rules["culture"] and state.culture_themes_missing:
        theme = sorted(state.culture_themes_missing)[0]
        add("culture", {"theme": theme, "theme_name": theme.replace("-", " ")})
    if weekday == 6 and (
        phase != "maintenance" or (state.today.day <= 7 and not state.deep_dive_done_this_month)
    ):
        live = [
            g
            for g in state.gaps
            if g.status in ("candidate", "verifying", "verified") and g.score_total >= 50
        ]
        live.sort(key=lambda g: (-g.score_total, -g.confidence))
        if live:
            add("deep-dive", _gap_payload(live[0]) | {"hypothesis": ""})
    # order by priority, then fit the budget greedily
    wanted.sort(key=lambda t: (-t.priority, t.profile))
    remaining = state.cap - state.spent_today
    planned: list[PlannedTask] = []
    for t in wanted:
        if t.est_cost_eur <= remaining:
            planned.append(t)
            remaining -= t.est_cost_eur
    return planned


def load_state(
    session, *, today: date, now: datetime, cap: Decimal, run_ids_today: list[int]
) -> PlannerState:
    from scout.seeds import CULTURE_THEMES

    sectors = [
        SectorInfo(s.slug, s.name_en, s.priority, s.status, s.last_mapped_at, s.last_hunted_at)
        for s in repo.list_sectors(session)
    ]
    have = {d.key for d in repo.list_digests(session, "culture:")}
    missing = [slug for slug, _name in CULTURE_THEMES if f"culture:{slug}" not in have]
    slug_by_id = {s.id: s.slug for s in repo.list_sectors(session)}
    gaps = [
        GapInfo(
            g.id,
            g.title,
            slug_by_id.get(g.sector_id, ""),
            g.score_total,
            g.confidence,
            g.status,
            repo.has_presence_check(session, g, now=now, max_age_days=30),
        )
        for g in repo.list_gaps(session)
    ]
    done_today: set[tuple[str, str]] = set()
    for run_id in run_ids_today:
        for t in repo.tasks_for_run(session, run_id):
            done_today.add(_key(t.profile, t.payload or {}))
    first = today.replace(day=1)
    deep_done = any(
        t.profile == "deep-dive" and t.status == "done"
        for rid in run_ids_today
        for t in repo.tasks_for_run(session, rid)
    ) or bool(repo.get_setting(session, f"deep-dive-done:{first.isoformat()}"))
    return PlannerState(
        today=today,
        sectors=sectors,
        culture_themes_missing=missing,
        gaps=gaps,
        open_field_checks=len(repo.open_field_checks(session)),
        spent_today=repo.spent_on(session, today),
        cap=cap,
        flagged_gap_ids=list(repo.get_setting(session, "flagged_gaps", []) or []),
        deep_dive_done_this_month=deep_done,
        done_today=done_today,
    )
