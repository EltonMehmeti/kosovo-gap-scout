from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from scout.db.base import Base, JSONType

MONEY = Numeric(12, 6)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    tier: Mapped[str] = mapped_column(String(1))
    name: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(40))
    base_url: Mapped[str | None] = mapped_column(Text)
    ttl_hours: Mapped[int] = mapped_column(Integer, default=24 * 30)
    cost_per_call_eur: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict | None] = mapped_column(JSONType)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_count: Mapped[int] = mapped_column(Integer, default=0)


class Digest(Base):
    __tablename__ = "digests"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body_md: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)


class Sector(Base):
    __tablename__ = "sectors"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name_en: Mapped[str] = mapped_column(String(200))
    name_sq: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="unmapped")
    presence_level: Mapped[str | None] = mapped_column(String(20))
    priority: Mapped[int] = mapped_column(Integer, default=50)
    last_mapped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_hunted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Business(Base):
    __tablename__ = "businesses"
    __table_args__ = (
        Index("ux_business_sector_name", "sector_id", text("lower(name)"), unique=True),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id"))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="local")
    city: Mapped[str | None] = mapped_column(String(80))
    channels: Mapped[dict | None] = mapped_column(JSONType)
    note: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProvenModel(Base):
    __tablename__ = "proven_models"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id"))
    description: Mapped[str] = mapped_column(Text)
    markets: Mapped[list] = mapped_column(JSONType, default=list)
    business_model: Mapped[str | None] = mapped_column(Text)
    source_urls: Mapped[list] = mapped_column(JSONType, default=list)
    nearby_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Gap(Base):
    __tablename__ = "gaps"
    __table_args__ = (Index("ux_gap_sector_title", "sector_id", text("lower(title)"), unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id"))
    proven_model_id: Mapped[int | None] = mapped_column(ForeignKey("proven_models.id"))
    hypothesis_md: Mapped[str] = mapped_column(Text, default="")
    presence_level: Mapped[str] = mapped_column(String(20), default="unknown")
    why_not_yet_md: Mapped[str] = mapped_column(Text, default="")
    test_plan_md: Mapped[str] = mapped_column(Text, default="")
    score_total: Mapped[int] = mapped_column(Integer, default=0)
    score_components: Mapped[dict | None] = mapped_column(JSONType)
    confidence: Mapped[float] = mapped_column(default=0.3)
    status: Mapped[str] = mapped_column(String(20), default="candidate")
    critic_flag: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_assessed_run_id: Mapped[int | None] = mapped_column(Integer)


class GapAssessment(Base):
    __tablename__ = "gap_assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    gap_id: Mapped[int] = mapped_column(ForeignKey("gaps.id"))
    run_id: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(60))
    strategist: Mapped[dict | None] = mapped_column(JSONType)
    critic: Mapped[dict | None] = mapped_column(JSONType)
    score_total: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FieldCheck(Base):
    __tablename__ = "field_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    gap_id: Mapped[int | None] = mapped_column(ForeignKey("gaps.id"))
    question: Mapped[str] = mapped_column(Text)
    why: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="open")
    answer: Mapped[str | None] = mapped_column(Text)
    due: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Fact(Base):
    __tablename__ = "facts"
    id: Mapped[int] = mapped_column(primary_key=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_key: Mapped[str] = mapped_column(String(160))
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"))
    claim: Mapped[str] = mapped_column(Text)
    value: Mapped[dict | None] = mapped_column(JSONType)
    confidence: Mapped[float] = mapped_column()
    source_name: Mapped[str] = mapped_column(String(80), default="web")
    source_url: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[int | None] = mapped_column(Integer)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="queued")
    priority: Mapped[int] = mapped_column(Integer, default=50)
    est_cost_eur: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    actual_cost_eur: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    result_md: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[int | None] = mapped_column(Integer)
    locked_by: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date)
    phase: Mapped[str] = mapped_column(String(20))
    budget_cap_eur: Mapped[Decimal] = mapped_column(MONEY)
    spent_eur: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    tasks_done: Mapped[int] = mapped_column(Integer, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="running")
    summary_md: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Cost(Base):
    __tablename__ = "costs"
    __table_args__ = (Index("ix_costs_day", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date)
    run_id: Mapped[int | None] = mapped_column(Integer)
    task_id: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(12))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str | None] = mapped_column(String(60))
    units: Mapped[dict] = mapped_column(JSONType, default=dict)
    cost_eur: Mapped[Decimal] = mapped_column(MONEY)
    request_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JournalEntry(Base):
    __tablename__ = "journal"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(Integer)
    day: Mapped[date] = mapped_column(Date)
    did_md: Mapped[str] = mapped_column(Text, default="")
    learned_md: Mapped[str] = mapped_column(Text, default="")
    tomorrow_md: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Scorecard(Base):
    __tablename__ = "scorecard"
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, unique=True)
    metrics: Mapped[dict] = mapped_column(JSONType, default=dict)


class AppChartSnapshot(Base):
    __tablename__ = "app_chart_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "store", "country", "chart", "app_key", "captured_on", name="ux_chart_row"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    store: Mapped[str] = mapped_column(String(10))
    country: Mapped[str] = mapped_column(String(2))
    chart: Mapped[str] = mapped_column(String(20), default="top-free")
    rank: Mapped[int] = mapped_column(Integer)
    app_key: Mapped[str] = mapped_column(String(200))
    app_name: Mapped[str] = mapped_column(String(200), default="")
    captured_on: Mapped[date] = mapped_column(Date)


class Brief(Base):
    __tablename__ = "briefs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(Integer)
    day: Mapped[date] = mapped_column(Date)
    markdown: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSONType)


class Ad(Base):
    __tablename__ = "ads"
    id: Mapped[int] = mapped_column(primary_key=True)
    ad_archive_id: Mapped[str] = mapped_column(String(40), unique=True)
    page_name: Mapped[str] = mapped_column(String(200), default="")
    page_url: Mapped[str | None] = mapped_column(Text)
    ad_text: Mapped[str] = mapped_column(Text, default="")
    platforms: Mapped[list] = mapped_column(JSONType, default=list)
    first_seen: Mapped[date | None] = mapped_column(Date)
    last_seen: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_foreign: Mapped[bool | None] = mapped_column(Boolean)
    sector_slug: Mapped[str | None] = mapped_column(String(80))
    gap_id: Mapped[int | None] = mapped_column(ForeignKey("gaps.id"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict | None] = mapped_column(JSONType)


class SocialCache(Base):
    __tablename__ = "social_cache"
    __table_args__ = (UniqueConstraint("source", "query_key", name="ux_social_cache_query"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20))
    query_key: Mapped[str] = mapped_column(String(320))
    items: Mapped[dict] = mapped_column(JSONType, default=dict)
    cost_usd: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
