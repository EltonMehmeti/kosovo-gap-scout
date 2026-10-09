from datetime import UTC, datetime, timedelta

import pytest

from scout.db import repo
from scout.db.repo import FactIn

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)


def test_slugify():
    assert repo.slugify("Home Services — Booking!") == "home-services-booking"


def test_upsert_fact_refreshes_same_claim(db_session):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    f = FactIn(
        claim="There are 3 pet shops in Prizren",
        entity_type="sector",
        entity_key="pets",
        confidence=0.5,
        sector_slug="pets",
        ttl_days=30,
    )
    a = repo.upsert_fact(db_session, f, run_id=1, observed_at=NOW)
    later = NOW + timedelta(days=2)
    f2 = FactIn(
        claim="  there are 3 PET shops in Prizren ",
        entity_type="sector",
        entity_key="pets",
        confidence=0.8,
        sector_slug="pets",
        ttl_days=30,
    )
    b = repo.upsert_fact(db_session, f2, run_id=2, observed_at=later)
    assert a.id == b.id
    assert b.confidence == 0.8
    assert b.observed_at == later
    assert b.expires_at == later + timedelta(days=30)
    assert len(repo.search_facts(db_session, "pet shops", now=later)) == 1


def test_search_excludes_expired(db_session):
    f = FactIn(
        claim="Old news about parking",
        entity_type="culture",
        entity_key="mobility",
        confidence=0.6,
        ttl_days=1,
    )
    repo.upsert_fact(db_session, f, run_id=None, observed_at=NOW)
    assert repo.search_facts(db_session, "parking", now=NOW) != []
    assert repo.search_facts(db_session, "parking", now=NOW + timedelta(days=2)) == []


def test_sector_digest_business_model_roundtrip(db_session):
    s = repo.get_or_create_sector(db_session, "pets", "Pets", "Kafshë", priority=2)
    assert repo.get_or_create_sector(db_session, "pets", "Pets").id == s.id
    repo.set_digest(db_session, "sector:pets", "Pets", "# Pets\nsmall market", now=NOW)
    assert repo.get_digest(db_session, "sector:pets") == "# Pets\nsmall market"
    b = repo.upsert_business(
        db_session,
        name="PetShop KS",
        sector_slug="pets",
        city="Prishtinë",
        channels={"instagram": "petshopks"},
        seen_at=NOW,
    )
    b2 = repo.upsert_business(
        db_session, name="petshop ks", sector_slug="pets", seen_at=NOW + timedelta(days=1)
    )
    assert b.id == b2.id and b2.channels == {"instagram": "petshopks"}
    assert b2.last_seen == NOW + timedelta(days=1)
    pm = repo.upsert_proven_model(
        db_session,
        slug="pet-sitting-marketplace",
        name="Pet sitting marketplace",
        sector_slug="pets",
        description="Rover-style",
        markets=[
            {"country": "HR", "example": "Pawshake", "url": "https://x"},
            {"country": "DE", "example": "Pawshake", "url": "https://y"},
        ],
    )
    assert pm.nearby_count == 1


def test_propose_gap_dedupes_by_title(db_session):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    g1, created1 = repo.propose_gap(db_session, title="Pet sitting marketplace", sector_slug="pets")
    g2, created2 = repo.propose_gap(
        db_session, title="PET SITTING marketplace", sector_slug="pets", hypothesis_md="x"
    )
    assert created1 and not created2 and g1.id == g2.id
    assert repo.list_gaps(db_session, statuses=["candidate"])[0].id == g1.id


def test_has_presence_check(db_session):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    gap, _ = repo.propose_gap(db_session, title="Pet sitting marketplace", sector_slug="pets")
    assert not repo.has_presence_check(db_session, gap, now=NOW)
    repo.upsert_fact(
        db_session,
        FactIn(
            claim="presence check: absent",
            entity_type="presence_check",
            entity_key=f"gap:{gap.id}",
            confidence=0.8,
            sector_slug="pets",
            value={"verdict": "absent"},
            ttl_days=60,
        ),
        run_id=1,
        observed_at=NOW,
    )
    assert repo.has_presence_check(db_session, gap, now=NOW)
    assert not repo.has_presence_check(db_session, gap, now=NOW + timedelta(days=61))
