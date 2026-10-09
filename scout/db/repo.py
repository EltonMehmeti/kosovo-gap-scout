"""Repository: every database read/write the engine needs, as plain functions."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from scout.db.models import (
    AppChartSnapshot,
    Brief,
    Business,
    Cost,
    Digest,
    Fact,
    FieldCheck,
    Gap,
    JournalEntry,
    ProvenModel,
    Run,
    Scorecard,
    Sector,
    Setting,
    Task,
)

NEARBY = {"AL", "MK", "ME", "BA", "RS", "HR", "SI"}


# ---------- helpers ----------


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()


def fact_hash(entity_type: str, entity_key: str, claim: str) -> str:
    raw = f"{entity_type}|{entity_key}|{_norm(claim)}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------- facts ----------


@dataclass
class FactIn:
    claim: str
    entity_type: str
    entity_key: str
    confidence: float
    source_url: str | None = None
    sector_slug: str | None = None
    value: dict | None = None
    ttl_days: int = 90
    source_name: str = "web"


def upsert_fact(session: Session, f: FactIn, *, run_id: int | None, observed_at: datetime) -> Fact:
    h = fact_hash(f.entity_type, f.entity_key, f.claim)
    sector = get_sector(session, f.sector_slug) if f.sector_slug else None
    fact = session.scalars(select(Fact).where(Fact.hash == h)).first()
    expires = observed_at + timedelta(days=f.ttl_days)
    if fact is None:
        fact = Fact(
            hash=h,
            entity_type=f.entity_type,
            entity_key=f.entity_key,
            sector_id=sector.id if sector else None,
            claim=f.claim.strip(),
            value=f.value,
            confidence=f.confidence,
            source_name=f.source_name,
            source_url=f.source_url,
            observed_at=observed_at,
            expires_at=expires,
            run_id=run_id,
        )
        session.add(fact)
    else:
        fact.observed_at = observed_at
        fact.expires_at = expires
        fact.confidence = max(fact.confidence, f.confidence)
        fact.source_url = f.source_url or fact.source_url
        fact.value = f.value if f.value is not None else fact.value
        fact.run_id = run_id
        if sector and fact.sector_id is None:
            fact.sector_id = sector.id
    session.commit()
    return fact


def search_facts(
    session: Session,
    query: str,
    *,
    sector_slug: str | None = None,
    limit: int = 20,
    now: datetime,
) -> list[Fact]:
    words = [w for w in re.split(r"\s+", query.strip()) if len(w) >= 3][:6]
    stmt = select(Fact).where(Fact.expires_at > now)
    for w in words:
        stmt = stmt.where(or_(Fact.claim.ilike(f"%{w}%"), Fact.entity_key.ilike(f"%{w}%")))
    if sector_slug:
        sector = get_sector(session, sector_slug)
        if sector:
            stmt = stmt.where(Fact.sector_id == sector.id)
    stmt = stmt.order_by(Fact.confidence.desc(), Fact.observed_at.desc()).limit(limit)
    return list(session.scalars(stmt))


def fresh_facts_since(
    session: Session,
    since: datetime,
    *,
    sector_slugs: list[str] | None = None,
    min_confidence: float = 0.0,
    now: datetime,
) -> list[Fact]:
    stmt = select(Fact).where(
        Fact.observed_at >= since, Fact.expires_at > now, Fact.confidence >= min_confidence
    )
    if sector_slugs:
        ids = [s.id for s in session.scalars(select(Sector).where(Sector.slug.in_(sector_slugs)))]
        stmt = stmt.where(Fact.sector_id.in_(ids))
    return list(session.scalars(stmt.order_by(Fact.confidence.desc()).limit(400)))


def latest_presence_check(
    session: Session, gap: Gap, *, now: datetime, max_age_days: int = 60
) -> Fact | None:
    """Newest unexpired presence_check fact for the gap from a complete protocol run (a `degraded`
    check — too few real searches in its task — is kept as evidence but never lifts the cap)."""
    stmt = (
        select(Fact)
        .where(
            Fact.entity_type == "presence_check",
            Fact.entity_key == f"gap:{gap.id}",
            Fact.observed_at >= now - timedelta(days=max_age_days),
            Fact.expires_at > now,
        )
        .order_by(Fact.observed_at.desc(), Fact.id.desc())
    )
    for fact in session.scalars(stmt):
        if not (isinstance(fact.value, dict) and fact.value.get("degraded")):
            return fact
    return None


def has_presence_check(
    session: Session, gap: Gap, *, now: datetime, max_age_days: int = 60
) -> bool:
    return latest_presence_check(session, gap, now=now, max_age_days=max_age_days) is not None


# ---------- sectors, digests ----------


def get_sector(session: Session, slug: str) -> Sector | None:
    return session.scalars(select(Sector).where(Sector.slug == slug)).first()


def get_or_create_sector(
    session: Session, slug: str, name_en: str, name_sq: str | None = None, priority: int = 50
) -> Sector:
    sector = get_sector(session, slug)
    if sector is None:
        sector = Sector(slug=slug, name_en=name_en, name_sq=name_sq, priority=priority)
        session.add(sector)
        session.commit()
    return sector


def list_sectors(session: Session) -> list[Sector]:
    return list(session.scalars(select(Sector).order_by(Sector.priority, Sector.slug)))


def set_sector_status(session: Session, slug: str, status: str, *, now: datetime) -> None:
    sector = get_sector(session, slug)
    if sector is None:
        return
    sector.status = status
    if status == "mapped":
        sector.last_mapped_at = now
    if status == "hunted":
        sector.last_hunted_at = now
    session.commit()


def get_digest(session: Session, key: str) -> str | None:
    d = session.get(Digest, key)
    return d.body_md if d else None


def set_digest(session: Session, key: str, title: str, body_md: str, *, now: datetime) -> Digest:
    d = session.get(Digest, key)
    if d is None:
        d = Digest(key=key, title=title)
        session.add(d)
    d.title = title
    d.body_md = body_md
    d.updated_at = now
    d.token_estimate = max(1, len(body_md) // 4)
    session.commit()
    return d


def list_digests(session: Session, prefix: str) -> list[Digest]:
    return list(
        session.scalars(select(Digest).where(Digest.key.like(f"{prefix}%")).order_by(Digest.key))
    )


# ---------- businesses, proven models, gaps ----------


def upsert_business(
    session: Session,
    *,
    name: str,
    sector_slug: str,
    kind: str = "local",
    city: str | None = None,
    channels: dict | None = None,
    note: str | None = None,
    seen_at: datetime,
) -> Business:
    sector = get_or_create_sector(session, sector_slug, sector_slug.replace("-", " ").title())
    stmt = select(Business).where(
        Business.sector_id == sector.id, func.lower(Business.name) == name.strip().lower()
    )
    b = session.scalars(stmt).first()
    if b is None:
        b = Business(
            sector_id=sector.id,
            name=name.strip(),
            kind=kind,
            city=city,
            channels=channels or {},
            note=note,
            first_seen=seen_at,
            last_seen=seen_at,
        )
        session.add(b)
    else:
        b.last_seen = max(b.last_seen, seen_at)
        b.city = city or b.city
        b.note = note or b.note
        merged = dict(b.channels or {})
        merged.update({k: v for k, v in (channels or {}).items() if v})
        b.channels = merged
    session.commit()
    return b


def list_businesses(session: Session, sector_slug: str) -> list[Business]:
    sector = get_sector(session, sector_slug)
    if sector is None:
        return []
    return list(
        session.scalars(
            select(Business).where(Business.sector_id == sector.id).order_by(Business.name)
        )
    )


def upsert_proven_model(
    session: Session,
    *,
    slug: str,
    name: str,
    sector_slug: str,
    description: str,
    markets: list[dict],
    business_model: str | None = None,
    source_urls: list[str] | None = None,
) -> ProvenModel:
    sector = get_or_create_sector(session, sector_slug, sector_slug.replace("-", " ").title())
    pm = session.scalars(select(ProvenModel).where(ProvenModel.slug == slug)).first()
    if pm is None:
        pm = ProvenModel(slug=slug, name=name, sector_id=sector.id, description=description)
        session.add(pm)
    pm.name = name
    pm.description = description
    existing = {(m.get("country"), m.get("example")) for m in (pm.markets or [])}
    merged = list(pm.markets or [])
    for m in markets:
        if (m.get("country"), m.get("example")) not in existing:
            merged.append(m)
    pm.markets = merged
    pm.business_model = business_model or pm.business_model
    pm.source_urls = sorted(set(pm.source_urls or []) | set(source_urls or []))
    pm.nearby_count = sum(1 for m in merged if str(m.get("country", "")).upper() in NEARBY)
    session.commit()
    return pm


def get_gap(session: Session, gap_id: int) -> Gap | None:
    return session.get(Gap, gap_id)


def get_gap_by_title(session: Session, sector_slug: str, title: str) -> Gap | None:
    sector = get_sector(session, sector_slug)
    if sector is None:
        return None
    return session.scalars(
        select(Gap).where(
            Gap.sector_id == sector.id, func.lower(Gap.title) == title.strip().lower()
        )
    ).first()


def propose_gap(
    session: Session,
    *,
    title: str,
    sector_slug: str,
    proven_model_slug: str | None = None,
    hypothesis_md: str = "",
    presence_level: str = "unknown",
    why_not_yet_md: str = "",
    run_id: int | None = None,
) -> tuple[Gap, bool]:
    sector = get_or_create_sector(session, sector_slug, sector_slug.replace("-", " ").title())
    gap = get_gap_by_title(session, sector_slug, title)
    pm = (
        session.scalars(select(ProvenModel).where(ProvenModel.slug == proven_model_slug)).first()
        if proven_model_slug
        else None
    )
    if gap is not None:
        gap.hypothesis_md = hypothesis_md or gap.hypothesis_md
        gap.why_not_yet_md = why_not_yet_md or gap.why_not_yet_md
        if presence_level != "unknown":
            gap.presence_level = presence_level  # verify-gap reports its verdict through this path
        if pm and gap.proven_model_id is None:
            gap.proven_model_id = pm.id
        session.commit()
        return gap, False
    gap = Gap(
        title=title.strip(),
        sector_id=sector.id,
        proven_model_id=pm.id if pm else None,
        hypothesis_md=hypothesis_md,
        presence_level=presence_level,
        why_not_yet_md=why_not_yet_md,
        status="candidate",
        last_assessed_run_id=run_id,
    )
    session.add(gap)
    session.commit()
    return gap, True


def list_gaps(
    session: Session,
    *,
    statuses: list[str] | None = None,
    min_score: int | None = None,
    sector_slugs: list[str] | None = None,
) -> list[Gap]:
    stmt = select(Gap)
    if statuses:
        stmt = stmt.where(Gap.status.in_(statuses))
    if min_score is not None:
        stmt = stmt.where(Gap.score_total >= min_score)
    if sector_slugs:
        ids = [s.id for s in session.scalars(select(Sector).where(Sector.slug.in_(sector_slugs)))]
        stmt = stmt.where(Gap.sector_id.in_(ids))
    return list(
        session.scalars(stmt.order_by(Gap.score_total.desc(), Gap.confidence.desc(), Gap.id))
    )


# ---------- task queue ----------


@dataclass
class CostRecord:
    kind: str
    provider: str
    model: str | None
    units: dict
    cost_eur: Decimal
    request_id: str | None = None
    task_id: int | None = None


@dataclass
class ChartEntryIn:
    rank: int
    app_key: str
    app_name: str


MAX_ATTEMPTS = 2
_ZERO = Decimal("0")


def enqueue_task(
    session: Session,
    *,
    profile: str,
    payload: dict,
    priority: int = 50,
    est_cost_eur: Decimal = _ZERO,
    run_id: int | None = None,
) -> Task:
    t = Task(
        profile=profile,
        payload=payload,
        priority=priority,
        est_cost_eur=est_cost_eur,
        run_id=run_id,
    )
    session.add(t)
    session.commit()
    return t


def claim_next_task(session: Session, worker_id: str, *, now: datetime) -> Task | None:
    stmt = (
        select(Task)
        .where(Task.status == "queued")
        .order_by(Task.priority.desc(), Task.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    task = session.scalars(stmt).first()
    if task is None:
        session.rollback()
        return None
    task.status = "running"
    task.started_at = now
    task.locked_by = worker_id
    task.attempts += 1
    session.commit()
    return task


def finish_task(
    session: Session, task: Task, *, result_md: str, actual_cost_eur: Decimal, now: datetime
) -> None:
    task.status = "done"
    task.result_md = result_md
    task.actual_cost_eur = actual_cost_eur
    task.finished_at = now
    task.locked_by = None
    session.commit()


def fail_task(session: Session, task: Task, *, error: str, now: datetime, requeue: bool) -> None:
    task.error = error[:4000]
    task.finished_at = now
    task.locked_by = None
    task.status = "queued" if (requeue and task.attempts < MAX_ATTEMPTS) else "failed"
    session.commit()


def queued_tasks(session: Session) -> list[Task]:
    return list(
        session.scalars(
            select(Task).where(Task.status == "queued").order_by(Task.priority.desc(), Task.id)
        )
    )


def tasks_for_run(session: Session, run_id: int | None) -> list[Task]:
    if run_id is None:
        return []
    return list(session.scalars(select(Task).where(Task.run_id == run_id).order_by(Task.id)))


def task_exists_today(
    session: Session, profile: str, payload_key: str, payload_value: str, day: date
) -> bool:
    run_ids = [r.id for r in session.scalars(select(Run).where(Run.day == day))]
    if not run_ids:
        return False
    for t in session.scalars(select(Task).where(Task.profile == profile, Task.run_id.in_(run_ids))):
        if str((t.payload or {}).get(payload_key)) == payload_value:
            return True
    return False


# ---------- runs, costs ----------


def start_run(
    session: Session, *, day: date, phase: str, budget_cap_eur: Decimal, started_at: datetime
) -> Run:
    run = Run(day=day, phase=phase, budget_cap_eur=budget_cap_eur, started_at=started_at)
    session.add(run)
    session.commit()
    return run


def finish_run(
    session: Session,
    run: Run,
    *,
    spent_eur: Decimal,
    tasks_done: int,
    tasks_failed: int,
    summary_md: str,
    finished_at: datetime,
    status: str = "done",
) -> None:
    run.spent_eur = spent_eur
    run.tasks_done = tasks_done
    run.tasks_failed = tasks_failed
    run.summary_md = summary_md
    run.finished_at = finished_at
    run.status = status
    session.commit()


def last_run(session: Session) -> Run | None:
    return session.scalars(select(Run).order_by(Run.id.desc())).first()


def record_cost(session: Session, rec: CostRecord, *, day: date, run_id: int | None) -> Cost:
    c = Cost(
        day=day,
        run_id=run_id,
        task_id=rec.task_id,
        kind=rec.kind,
        provider=rec.provider,
        model=rec.model,
        units=rec.units,
        cost_eur=rec.cost_eur,
        request_id=rec.request_id,
    )
    session.add(c)
    session.commit()
    return c


def spent_on(session: Session, day: date) -> Decimal:
    total = session.scalar(select(func.coalesce(func.sum(Cost.cost_eur), 0)).where(Cost.day == day))
    return Decimal(total).quantize(Decimal("0.000001"))


def spent_between(session: Session, start: date, end: date) -> Decimal:
    total = session.scalar(
        select(func.coalesce(func.sum(Cost.cost_eur), 0)).where(Cost.day >= start, Cost.day <= end)
    )
    return Decimal(total).quantize(Decimal("0.000001"))


def places_calls_in_month(session: Session, day: date) -> int:
    start = day.replace(day=1)
    rows = session.scalars(
        select(Cost).where(Cost.kind == "places", Cost.day >= start, Cost.day <= day)
    )
    return sum(int((c.units or {}).get("calls", 1)) for c in rows)


# ---------- journal, briefs, scorecard, settings ----------


def write_journal(
    session: Session,
    *,
    run_id: int | None,
    day: date,
    did_md: str,
    learned_md: str,
    tomorrow_md: str,
) -> JournalEntry:
    j = JournalEntry(
        run_id=run_id, day=day, did_md=did_md, learned_md=learned_md, tomorrow_md=tomorrow_md
    )
    session.add(j)
    session.commit()
    return j


def latest_journal(session: Session, limit: int = 3) -> list[JournalEntry]:
    return list(session.scalars(select(JournalEntry).order_by(JournalEntry.id.desc()).limit(limit)))


def save_brief(session: Session, *, run_id: int | None, day: date, markdown: str) -> Brief:
    b = Brief(run_id=run_id, day=day, markdown=markdown)
    session.add(b)
    session.commit()
    return b


def latest_brief(session: Session) -> Brief | None:
    return session.scalars(select(Brief).order_by(Brief.id.desc())).first()


def save_scorecard(session: Session, *, day: date, metrics: dict) -> Scorecard:
    sc = session.scalars(select(Scorecard).where(Scorecard.day == day)).first()
    if sc is None:
        sc = Scorecard(day=day, metrics=metrics)
        session.add(sc)
    else:
        sc.metrics = metrics
    session.commit()
    return sc


def get_setting(session: Session, key: str, default=None):
    s = session.get(Setting, key)
    return s.value if s is not None else default


def set_setting(session: Session, key: str, value) -> None:
    s = session.get(Setting, key)
    if s is None:
        session.add(Setting(key=key, value=value))
    else:
        s.value = value
    session.commit()


# ---------- app charts ----------


def save_chart_snapshot(
    session: Session,
    *,
    store: str,
    country: str,
    chart: str,
    entries: list[ChartEntryIn],
    captured_on: date,
) -> int:
    existing = {
        r.app_key
        for r in chart_snapshot(
            session, store=store, country=country, chart=chart, captured_on=captured_on
        )
    }
    added = 0
    for e in entries:
        if e.app_key in existing:
            continue
        session.add(
            AppChartSnapshot(
                store=store,
                country=country,
                chart=chart,
                rank=e.rank,
                app_key=e.app_key,
                app_name=e.app_name[:200],
                captured_on=captured_on,
            )
        )
        added += 1
    session.commit()
    return added


def chart_snapshot(
    session: Session, *, store: str, country: str, chart: str, captured_on: date
) -> list[AppChartSnapshot]:
    stmt = (
        select(AppChartSnapshot)
        .where(
            AppChartSnapshot.store == store,
            AppChartSnapshot.country == country,
            AppChartSnapshot.chart == chart,
            AppChartSnapshot.captured_on == captured_on,
        )
        .order_by(AppChartSnapshot.rank)
    )
    return list(session.scalars(stmt))


def latest_chart_date(
    session: Session, *, store: str, country: str, chart: str, before: date
) -> date | None:
    return session.scalar(
        select(func.max(AppChartSnapshot.captured_on)).where(
            AppChartSnapshot.store == store,
            AppChartSnapshot.country == country,
            AppChartSnapshot.chart == chart,
            AppChartSnapshot.captured_on < before,
        )
    )


def app_ever_in_chart(session: Session, *, store: str, country: str, app_key: str) -> bool:
    stmt = (
        select(AppChartSnapshot.id)
        .where(
            AppChartSnapshot.store == store,
            AppChartSnapshot.country == country,
            AppChartSnapshot.app_key == app_key,
        )
        .limit(1)
    )
    return session.scalar(stmt) is not None


# ---------- field checks ----------


def add_field_check(
    session: Session, *, gap_id: int | None, question: str, why: str, due: date
) -> FieldCheck:
    fc = FieldCheck(gap_id=gap_id, question=question, why=why, due=due)
    session.add(fc)
    session.commit()
    return fc


def open_field_checks(session: Session) -> list[FieldCheck]:
    return list(
        session.scalars(
            select(FieldCheck)
            .where(FieldCheck.status == "open")
            .order_by(FieldCheck.due, FieldCheck.id)
        )
    )


def answer_field_check(
    session: Session, fc: FieldCheck, *, answer: str, answered_at: datetime
) -> None:
    fc.answer = answer
    fc.status = "answered"
    fc.answered_at = answered_at
    session.commit()


def set_gap_test_plan(session: Session, gap_id: int, md: str) -> None:
    gap = session.get(Gap, gap_id)
    if gap is not None:
        gap.test_plan_md = md
        session.commit()


def runs_on_day(session: Session, day: date) -> list[Run]:
    return list(session.scalars(select(Run).where(Run.day == day).order_by(Run.id)))


def release_stale_tasks(session: Session, *, claimed_before: datetime) -> int:
    """Put tasks stuck in 'running' (claimed before the cutoff) back in the queue."""
    stale = list(
        session.scalars(
            select(Task).where(Task.status == "running", Task.started_at < claimed_before)
        )
    )
    for t in stale:
        t.status = "queued"
        t.locked_by = None
    session.commit()
    return len(stale)


def release_task(session: Session, task: Task, *, give_back_attempt: bool = False) -> None:
    """Return a claimed, unfinished task to the queue (optionally undoing the claim's attempt)."""
    task.status = "queued"
    task.locked_by = None
    if give_back_attempt and task.attempts > 0:
        task.attempts -= 1
    session.commit()
