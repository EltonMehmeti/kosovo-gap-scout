"""Founder actions, shared by the CLI and the dashboard. Spec A10: hand changes go through here,
and every one is journaled. Founder lines go into one journal entry per day (run_id NULL), which the
scout reads back as memory."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from scout.config import Settings
from scout.db import repo
from scout.db.models import Digest, FieldCheck, Gap, JournalEntry, Sector, Task
from scout.db.repo import FactIn
from scout.director.planner import PHASE_RULES, PHASES
from scout.worker.profiles import PROFILES

GAP_ACTIONS = {"park": "parked", "kill": "killed", "reopen": "candidate"}
TASK_PROFILES: tuple[str, ...] = (*PROFILES, "chart-diff")
MAX_TODAY_CAP_EUR = Decimal("10.00")


class FounderError(ValueError):
    """A founder action was refused; the message is safe to show as-is."""


def journal(session: Session, *, today: date, line: str) -> None:
    entry = session.scalars(
        select(JournalEntry)
        .where(JournalEntry.run_id.is_(None), JournalEntry.day == today)
        .order_by(JournalEntry.id)
    ).first()
    if entry is None:
        entry = JournalEntry(run_id=None, day=today, did_md="", learned_md="", tomorrow_md="")
        session.add(entry)
    entry.did_md = f"{entry.did_md}\n- Founder: {line}".lstrip("\n")
    session.commit()


def _gap(session: Session, gap_id: int) -> Gap:
    gap = repo.get_gap(session, gap_id)
    if gap is None:
        raise FounderError(f"unknown gap {gap_id}")
    return gap


def _ids(session: Session, key: str) -> list[int]:
    return [int(i) for i in (repo.get_setting(session, key, []) or [])]


def flagged(session: Session) -> list[int]:
    return _ids(session, "flagged_gaps")


def finalists(session: Session) -> list[int]:
    return _ids(session, "finalists")


def set_gap_status(
    session: Session, gap_id: int, action: str, *, today: date, now: datetime
) -> Gap:
    if action not in GAP_ACTIONS:
        raise FounderError(f"action must be one of {', '.join(GAP_ACTIONS)}")
    gap = _gap(session, gap_id)
    old = gap.status
    gap.status = GAP_ACTIONS[action]
    gap.updated_at = now
    session.commit()
    if action == "kill":  # a killed gap is neither verified next nor a finalist
        repo.set_setting(session, "flagged_gaps", [g for g in flagged(session) if g != gap_id])
        repo.set_setting(session, "finalists", [g for g in finalists(session) if g != gap_id])
    journal(
        session, today=today, line=f'{action} gap #{gap.id} "{gap.title}" ({old} → {gap.status})'
    )
    return gap


def flag_gap(session: Session, gap_id: int, *, today: date, unflag: bool = False) -> list[int]:
    """'Verify this': one flagged gap per day is verified first; the flag clears when it completes."""
    gap = _gap(session, gap_id)
    if not unflag and gap.status == "killed":
        raise FounderError("this gap is killed; reopen it before asking to verify it")
    current = flagged(session)
    ids = [g for g in current if g != gap_id] if unflag else sorted({*current, gap_id})
    repo.set_setting(session, "flagged_gaps", ids)
    verb = "withdrew verify request for" if unflag else "asked to verify"
    journal(session, today=today, line=f'{verb} gap #{gap.id} "{gap.title}"')
    return ids


def toggle_finalist(session: Session, gap_id: int, *, today: date) -> list[int]:
    gap = _gap(session, gap_id)
    current = finalists(session)
    if gap_id in current:
        ids, verb = [g for g in current if g != gap_id], "removed finalist"
    else:
        if gap.status == "killed":
            raise FounderError("a killed gap cannot be a finalist")
        ids, verb = sorted({*current, gap_id}), "chose as finalist"
    repo.set_setting(session, "finalists", ids)
    journal(session, today=today, line=f'{verb} gap #{gap.id} "{gap.title}"')
    return ids


def answer_field_check(
    session: Session, check_id: int, answer: str, *, today: date, now: datetime
) -> FieldCheck:
    """Spec B12: the answer becomes a fact (confidence 0.95, source founder), the check closes, and
    a verify-gap for its gap is queued at priority 90."""
    answer = answer.strip()
    if not answer:
        raise FounderError("the answer is empty")
    fc = session.get(FieldCheck, check_id)
    if fc is None or fc.status != "open":
        raise FounderError(f"no open field check #{check_id}")
    gap = repo.get_gap(session, fc.gap_id) if fc.gap_id else None
    sec = next((x for x in repo.list_sectors(session) if gap and x.id == gap.sector_id), None)
    repo.upsert_fact(
        session,
        FactIn(
            claim=f"Founder field check — Q: {fc.question} A: {answer}",
            entity_type="gap",
            entity_key=f"gap:{fc.gap_id}" if fc.gap_id else "general",
            confidence=0.95,
            sector_slug=sec.slug if sec else None,
            ttl_days=180,
            source_name="founder",
        ),
        run_id=None,
        observed_at=now,
    )
    repo.answer_field_check(session, fc, answer=answer, answered_at=now)
    if gap is not None:
        repo.enqueue_task(
            session,
            profile="verify-gap",
            priority=90,
            est_cost_eur=PROFILES["verify-gap"].est_cost_eur,
            payload={"gap_id": gap.id, "gap_title": gap.title, "sector": sec.slug if sec else ""},
        )
    journal(session, today=today, line=f"answered field check #{fc.id}: {fc.question} → {answer}")
    return fc


def add_task(
    session: Session,
    profile: str,
    *,
    today: date,
    sector: str | None = None,
    gap_id: int | None = None,
    theme: str | None = None,
    priority: int = 70,
) -> Task:
    if profile not in TASK_PROFILES:
        raise FounderError(f"profile must be one of {', '.join(TASK_PROFILES)}")
    if not 0 <= priority <= 100:
        raise FounderError("priority must be between 0 and 100")
    payload: dict = {}
    if sector:
        sec = repo.get_sector(session, sector)
        if sec is None:
            raise FounderError(f"unknown sector {sector}")
        payload = {"sector": sec.slug, "sector_name": sec.name_en}
    if gap_id is not None:
        gap = _gap(session, gap_id)
        sec = next((x for x in repo.list_sectors(session) if x.id == gap.sector_id), None)
        payload = {"gap_id": gap.id, "gap_title": gap.title, "sector": sec.slug if sec else ""}
    if theme:
        payload = {"theme": theme, "theme_name": theme.replace("-", " ")}
    payload["founder"] = True  # the director review never drops a task the founder queued
    est = PROFILES[profile].est_cost_eur if profile in PROFILES else Decimal("0.05")
    task = repo.enqueue_task(
        session, profile=profile, payload=payload, priority=priority, est_cost_eur=est
    )
    shown = {k: v for k, v in payload.items() if k != "founder"}
    journal(session, today=today, line=f"queued {profile} task #{task.id} {shown}")
    return task


def retry_task(session: Session, task_id: int, *, today: date) -> Task:
    task = session.get(Task, task_id)
    if task is None or task.status != "failed":
        raise FounderError(f"task #{task_id} is not failed")
    task.status, task.attempts, task.error, task.locked_by = "queued", 0, None, None
    task.payload = {**(task.payload or {}), "founder": True}  # new dict so the JSON change is saved
    session.commit()
    journal(session, today=today, line=f"retried {task.profile} task #{task.id}")
    return task


def edit_digest(session: Session, key: str, body_md: str, *, today: date, now: datetime) -> Digest:
    digest = session.get(Digest, key)
    if digest is None:
        raise FounderError(f"unknown digest {key}")
    saved = repo.set_digest(session, key, digest.title, body_md, now=now)
    journal(session, today=today, line=f"edited digest {key}")
    return saved


def set_phase(session: Session, phase: str, *, today: date) -> None:
    if phase not in PHASES:
        raise FounderError(f"phase must be one of {', '.join(PHASES)}")
    repo.set_setting(session, "phase", {"value": phase})
    journal(session, today=today, line=f"set phase to {phase}")


def set_sector_priority(session: Session, slug: str, priority: int, *, today: date) -> Sector:
    if not 0 <= priority <= 100:
        raise FounderError("priority must be between 0 and 100")
    sector = repo.get_sector(session, slug)
    if sector is None:
        raise FounderError(f"unknown sector {slug}")
    old, sector.priority = sector.priority, priority
    session.commit()
    journal(session, today=today, line=f"set sector {slug} priority {old} → {priority}")
    return sector


def _cap_key(today: date) -> str:
    return f"cap:{today.isoformat()}"


def set_today_cap(session: Session, eur: str | Decimal | None, *, today: date) -> Decimal | None:
    raw = "" if eur is None else str(eur).strip()
    if not raw:
        repo.set_setting(session, _cap_key(today), None)
        journal(session, today=today, line="cleared today's cap")
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise FounderError("the cap must be a number of euros, like 1.50") from None
    if not value.is_finite() or not Decimal("0") <= value <= MAX_TODAY_CAP_EUR:
        raise FounderError(f"the cap must be between €0 and €{MAX_TODAY_CAP_EUR}")
    value = value.quantize(Decimal("0.01"))
    repo.set_setting(session, _cap_key(today), {"value": str(value)})
    journal(session, today=today, line=f"set today's cap to €{value}")
    return value


def today_cap(session: Session, today: date) -> Decimal | None:
    v = repo.get_setting(session, _cap_key(today))
    return Decimal(v["value"]) if isinstance(v, dict) and v.get("value") is not None else None


def effective_cap(session: Session, settings: Settings, phase: str, today: date) -> Decimal:
    """The founder's cap for today if set; otherwise the phase cap limited by SCOUT_DAILY_BUDGET_EUR."""
    founder_cap = today_cap(session, today)
    if founder_cap is not None:
        return founder_cap
    return min(PHASE_RULES[phase]["cap"], Decimal(settings.daily_budget_eur))
