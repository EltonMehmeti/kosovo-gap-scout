"""Repository: every database read/write the engine needs, as plain functions."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from scout.db.models import (
    Business,
    Digest,
    Fact,
    Gap,
    ProvenModel,
    Sector,
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


def has_presence_check(
    session: Session, gap: Gap, *, now: datetime, max_age_days: int = 60
) -> bool:
    stmt = select(Fact).where(
        Fact.entity_type == "presence_check",
        Fact.entity_key == f"gap:{gap.id}",
        Fact.observed_at >= now - timedelta(days=max_age_days),
    )
    return session.scalars(stmt).first() is not None


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
