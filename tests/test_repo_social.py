from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from scout.db import repo
from scout.db.models import Source
from scout.db.repo import CostRecord, FactIn

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)


def _ad(archive_id="111", **over):
    base = {
        "ad_archive_id": archive_id,
        "page_name": "Torta Shop",
        "page_url": "https://facebook.com/tortashop",
        "ad_text": "Porosit torten",
        "platforms": ["facebook"],
        "first_seen": "2026-09-01",
        "last_seen": "2026-10-10",
        "is_active": True,
        "is_foreign": False,
        "link_url": "https://tortashop.rks",
    }
    return base | over


def test_apify_usd_counts_only_apify_rows_of_the_month(db_session):
    for day, kind, usd in (
        (date(2026, 9, 30), "apify", "1.00"),
        (date(2026, 10, 1), "apify", "0.25"),
        (date(2026, 10, 18), "apify", "0.50"),
        (date(2026, 10, 18), "places", "9.00"),
    ):
        repo.record_cost(
            db_session,
            CostRecord(kind, "x", None, {"usd": usd}, Decimal("0")),
            day=day,
            run_id=None,
        )
    assert repo.apify_usd_in_month(db_session, date(2026, 10, 19)) == Decimal("0.75")


def test_social_cache_round_trip_and_expiry(db_session):
    repo.put_social_cache(
        db_session, "instagram", "torta|30", {"shops": []}, cost_usd=Decimal("0.05"), now=NOW
    )
    hit = repo.get_social_cache(
        db_session, "instagram", "torta|30", now=NOW + timedelta(days=29), max_age_days=30
    )
    assert hit is not None and hit.items == {"shops": []}
    assert (
        repo.get_social_cache(
            db_session, "instagram", "torta|30", now=NOW + timedelta(days=31), max_age_days=30
        )
        is None
    )
    repo.put_social_cache(
        db_session, "instagram", "torta|30", {"shops": [1]}, cost_usd=Decimal("0"), now=NOW
    )
    assert repo.get_social_cache(
        db_session, "instagram", "torta|30", now=NOW, max_age_days=30
    ).items == {"shops": [1]}


def test_upsert_ads_updates_by_archive_id(db_session):
    repo.get_or_create_sector(db_session, "food", "Food")
    gap, _ = repo.propose_gap(db_session, title="Cake delivery", sector_slug="food")
    repo.upsert_ads(db_session, [_ad()], gap_id=gap.id, sector_slug="food", now=NOW)
    repo.upsert_ads(
        db_session,
        [_ad(last_seen="2026-10-19", is_active=False)],
        gap_id=None,
        sector_slug=None,
        now=NOW,
    )
    ads = repo.ads_for_gap(db_session, gap.id)
    assert len(ads) == 1
    assert ads[0].last_seen == date(2026, 10, 19) and ads[0].is_active is False
    assert ads[0].gap_id == gap.id and ads[0].sector_slug == "food"
    assert ads[0].raw == {"link_url": "https://tortashop.rks"}


def test_social_facts_for_gap_only_fresh_social_types(db_session):
    for etype, key in (
        ("social", "gap:7"),
        ("ad_signal", "gap:7"),
        ("gap", "gap:7"),
        ("social", "gap:8"),
    ):
        repo.upsert_fact(
            db_session,
            FactIn(claim=f"{etype} {key}", entity_type=etype, entity_key=key, confidence=0.7),
            run_id=None,
            observed_at=NOW,
        )
    facts = repo.social_facts_for_gap(db_session, 7, now=NOW)
    assert sorted(f.entity_type for f in facts) == ["ad_signal", "social"]


def test_mark_source(db_session):
    db_session.add(Source(tier="B", name="apify-instagram", kind="social", enabled=False))
    db_session.commit()
    repo.mark_source(db_session, "apify-instagram", ok=False, now=NOW)
    repo.mark_source(db_session, "apify-instagram", ok=True, now=NOW)
    repo.mark_source(db_session, "no-such-source", ok=True, now=NOW)
    src = db_session.query(Source).filter_by(name="apify-instagram").one()
    assert src.failure_count == 1 and src.enabled is True and src.last_ok_at == NOW
