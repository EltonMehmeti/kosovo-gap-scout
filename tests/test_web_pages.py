# tests/test_web_pages.py
"""Checks every page must pass: renders with data, no inline handlers, icons exist, plain header."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout.db import repo
from scout.db.models import GapAssessment
from scout.seeds import seed_all
from scout.web import deps

pytestmark = pytest.mark.db
SECTION_PAGES = (
    "/",
    "/gaps",
    "/field-checks",
    "/pipeline",
    "/journal",
    "/knowledge",
    "/costs",
    "/settings",
)
SPRITE = set(re.findall(r'id="i-([a-z-]+)"', (deps.STATIC_DIR / "icons.svg").read_text()))


@pytest.fixture
def populated(db_session):
    seed_all(db_session)
    gap, _ = repo.propose_gap(
        db_session, title="Pet sitting", sector_slug="pets", hypothesis_md="h"
    )
    db_session.add(
        GapAssessment(
            gap_id=gap.id,
            model="m",
            strategist={},
            critic={"risk": "x"},
            score_total=50,
            confidence=0.5,
        )
    )
    gap.score_components = {"proof": 10, "absence": 10, "demand": 10, "founder_fit": 10, "risk": 10}
    gap.score_total = 50
    db_session.commit()
    repo.add_field_check(db_session, gap_id=gap.id, question="q?", why="w", due=date(2026, 10, 11))
    run = repo.start_run(
        db_session,
        day=date(2026, 10, 9),
        phase="foundation",
        budget_cap_eur=Decimal("1.00"),
        started_at=datetime(2026, 10, 9, 6, tzinfo=UTC),
    )
    t = repo.enqueue_task(db_session, profile="news-scan", payload={}, priority=40, run_id=run.id)
    t.status, t.error = "failed", "boom"
    db_session.commit()
    repo.enqueue_task(db_session, profile="map-sector", payload={"sector": "pets"}, priority=70)
    repo.save_brief(db_session, run_id=run.id, day=date(2026, 10, 9), markdown="# Brief")
    repo.write_journal(
        db_session, run_id=run.id, day=date(2026, 10, 9), did_md="d", learned_md="", tomorrow_md=""
    )
    repo.set_digest(db_session, "sector:pets", "Pets", "## Vets", now=datetime.now(UTC))
    return gap


def _pages(gap):
    return (
        *SECTION_PAGES,
        f"/gaps/{gap.id}",
        "/knowledge/sectors/pets",
        "/knowledge/digests/sector:pets",
        "/knowledge?q=pets",
    )


def test_every_page_renders_without_inline_handlers_and_with_real_icons(web, populated):
    for path in _pages(populated):
        r = web.get(path)
        assert r.status_code == 200, path
        assert not re.search(r"\son[a-z]+=", r.text), f"inline event handler on {path}"
        assert "<script>" not in r.text, path
        for name in re.findall(r"icons\.svg\?v=[0-9a-f]+#i-([a-z-]+)", r.text):
            assert name in SPRITE, f"{path} uses missing icon {name}"


def test_every_section_page_explains_itself(web, populated):
    for path in SECTION_PAGES:
        html = web.get(path).text
        assert '<header class="page-head">' in html and '<p class="subtitle">' in html, path


def test_no_raw_status_words_on_the_board(web, populated):
    html = web.get("/gaps").text
    assert ">candidate<" not in html and ">killed<" not in html


def test_login_and_error_pages_have_no_inline_handlers(web, db_session, db_engine, settings):
    assert not re.search(r"\son[a-z]+=", web.get("/gaps/99999999999").text)
    from fastapi.testclient import TestClient

    from scout.db.base import make_session_factory
    from scout.web.app import create_app

    anon = TestClient(
        create_app(settings, make_session_factory(db_engine)), base_url="https://testserver"
    )
    assert not re.search(r"\son[a-z]+=", anon.get("/login").text)


def test_the_old_gap_actions_partial_is_gone():
    assert not (deps.STATIC_DIR.parent / "templates" / "_gap_actions.html").exists()


def test_costs_page_shows_social_credit(web, db_session):
    from datetime import UTC, datetime
    from decimal import Decimal
    from zoneinfo import ZoneInfo

    from scout.db import repo
    from scout.db.repo import CostRecord

    today = datetime.now(UTC).astimezone(ZoneInfo("Europe/Belgrade")).date()
    repo.record_cost(
        db_session,
        CostRecord("apify", "apify", "ads", {"usd": "1.25"}, Decimal("0")),
        day=today,
        run_id=None,
    )
    html = web.get("/costs").text
    assert "Social credit" in html and "$1.25" in html and "$4.50" in html
