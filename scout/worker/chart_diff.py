"""Weekly app-chart diff: apps charting in ≥ 2 neighbours but never in Kosovo are cheap, strong leads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from scout.db import repo
from scout.db.repo import ChartEntryIn, FactIn
from scout.extract.extractor import Extractor
from scout.extract.schemas import AppClassificationBatch
from scout.sources import apple, play

CHART_COUNTRIES = ("xk", "al", "mk", "me", "ba", "rs", "hr", "si")
NEIGHBOURS = CHART_COUNTRIES[1:]
CHART = "top-free"


@dataclass
class Lead:
    store: str
    app_key: str
    name: str
    publisher: str
    countries: list[str] = field(default_factory=list)
    best_rank: int = 999


@dataclass
class ChartDiffReport:
    captured_on: date
    snapshots_saved: int = 0
    leads: list[Lead] = field(default_factory=list)
    new_in_kosovo: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run_chart_diff(
    session,
    today: date,
    *,
    apple_fetch=apple.fetch_top_free,
    play_fetch=play.fetch_top_free,
    min_neighbours: int = 2,
) -> ChartDiffReport:
    report = ChartDiffReport(captured_on=today)
    for store, fetch in (("apple", apple_fetch), ("play", play_fetch)):
        charts: dict[str, list] = {}
        for country in CHART_COUNTRIES:
            try:
                charts[country] = list(fetch(country))
            except Exception as e:  # noqa: BLE001 — one dead storefront must not stop the others
                report.errors.append(f"{store}/{country}: {type(e).__name__}: {e}")
        for country, entries in charts.items():
            report.snapshots_saved += repo.save_chart_snapshot(
                session,
                store=store,
                country=country,
                chart=CHART,
                entries=[ChartEntryIn(e.rank, e.app_key, e.name) for e in entries],
                captured_on=today,
            )
        if "xk" not in charts:
            continue  # cannot diff without the Kosovo chart
        xk_keys = {(store, e.app_key) for e in charts["xk"]}
        candidates: dict[tuple[str, str], Lead] = {}
        for country in NEIGHBOURS:
            for e in charts.get(country, []):
                if (store, e.app_key) in xk_keys:
                    continue
                lead = candidates.setdefault(
                    (store, e.app_key), Lead(store, e.app_key, e.name, e.publisher)
                )
                lead.countries.append(country)
                lead.best_rank = min(lead.best_rank, e.rank)
        for lead in candidates.values():
            if len(lead.countries) >= min_neighbours and not repo.app_ever_in_chart(
                session, store=store, country="xk", app_key=lead.app_key
            ):
                report.leads.append(lead)
        previous = repo.latest_chart_date(
            session, store=store, country="xk", chart=CHART, before=today
        )
        if previous is not None:
            prev_keys = {
                r.app_key
                for r in repo.chart_snapshot(
                    session, store=store, country="xk", chart=CHART, captured_on=previous
                )
            }
            report.new_in_kosovo += [e.name for e in charts["xk"] if e.app_key not in prev_keys]
    report.leads.sort(key=lambda lead: (-len(lead.countries), lead.best_rank))
    return report


CLASSIFY_INSTRUCTIONS = (
    "Each line is an app that ranks in the top-free chart of neighbouring countries but not in Kosovo. "
    "For each app give: category, the consumer need it serves (one sentence), kosovo_relevance (high if a "
    "Kosovo consumer plausibly has the same need and no local equivalent is known, low for global brands, "
    "games, carrier or bank apps tied to one country), the closest sector_slug from this list or 'none': "
    "home-services, health-booking, tutoring-education, mobility-transit, secondhand-marketplaces, "
    "rentals-housing, diaspora-services, weddings-events, food-grocery-delivery, beauty-wellness, "
    "fitness-sports, pets, car-services, parenting-kids, bureaucracy-helpers, local-travel, "
    "utilities-household-finance, jobs-gigs, agri-to-consumer, entertainment-media, legal-consumer, "
    "instagram-seller-tools, elderly-care, language-ai-consumer; and is_global_brand."
)


def classify_and_record(
    session,
    extractor: Extractor,
    report: ChartDiffReport,
    *,
    now: datetime,
    run_id: int | None,
    max_leads: int = 10,
    play_details=play.app_details,
) -> int:
    leads = report.leads[:max_leads]
    if not leads:
        return 0
    for lead in leads:
        if lead.store == "play" and lead.name == lead.app_key:
            try:
                hit = play_details(lead.app_key, country="xk")
                lead.name, lead.publisher = hit.name or lead.name, hit.publisher or lead.publisher
            except Exception:  # noqa: BLE001 — a missing title is not worth failing the run
                pass
    text = "\n".join(
        f"{lead.store} | {lead.app_key} | {lead.name} | {lead.publisher} | "
        f"countries={','.join(lead.countries)} | best_rank={lead.best_rank}"
        for lead in leads
    )
    batch = extractor.extract(AppClassificationBatch, CLASSIFY_INSTRUCTIONS, text)
    by_key: dict[str, list[Lead]] = {}
    for lead in leads:
        by_key.setdefault(lead.app_key, []).append(lead)
    written = 0
    for item in batch.items:
        if item.is_global_brand or item.kosovo_relevance == "low":
            continue
        # The model echoes only app_key; if two stores share a key, each lead keeps its own fact.
        for lead in by_key.get(item.app_key, []):
            written += _record(session, lead, item, now=now, run_id=run_id)
    return written


def _record(session, lead: Lead, item, *, now: datetime, run_id: int | None) -> int:
    sector_slug = item.sector_slug if repo.get_sector(session, item.sector_slug) else None
    repo.upsert_fact(
        session,
        FactIn(
            claim=(
                f"App '{lead.name}' ({lead.store}) charts top-free in {', '.join(lead.countries)} but not in "
                f"Kosovo — {item.consumer_need}"
            ),
            entity_type="stat",
            entity_key=f"app:{lead.store}:{lead.app_key}",
            confidence=0.6,
            source_url=None,
            sector_slug=sector_slug,
            ttl_days=30,
            value={
                "store": lead.store,
                "app_key": lead.app_key,
                "countries": lead.countries,
                "best_rank": lead.best_rank,
                "category": item.category,
                "relevance": item.kosovo_relevance,
                "sector_slug": item.sector_slug,
            },
        ),
        run_id=run_id,
        observed_at=now,
    )
    return 1
