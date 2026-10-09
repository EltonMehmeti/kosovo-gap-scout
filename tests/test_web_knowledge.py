from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout import founder
from scout.db import repo
from scout.db.repo import CostRecord, FactIn
from scout.seeds import seed_all

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)


def test_pages_render_on_an_empty_database(web):
    for path in ("/knowledge", "/costs", "/settings"):
        assert web.get(path).status_code == 200


def test_knowledge_sector_digest_and_fact_search(web, db_session):
    seed_all(db_session)
    repo.set_digest(db_session, "sector:pets", "Pets", "## Vets\n<script>x</script>", now=NOW)
    repo.upsert_business(db_session, sector_slug="pets", name="PetVet Prishtina", seen_at=NOW)
    repo.upsert_fact(
        db_session,
        FactIn(
            claim="No pet sitting apps in Kosovo",
            entity_type="sector",
            entity_key="pets",
            confidence=0.7,
            sector_slug="pets",
        ),
        run_id=None,
        observed_at=datetime.now(UTC),
    )
    assert "Pets (vets, sitting, supplies)" in web.get("/knowledge").text
    s = web.get("/knowledge/sectors/pets")
    assert "<h2>Vets</h2>" in s.text and "&lt;script&gt;" in s.text and "PetVet Prishtina" in s.text
    assert web.get("/knowledge/sectors/nope").status_code == 404
    assert "No pet sitting apps" in web.get("/knowledge", params={"q": "sitting apps"}).text
    r = web.post("/knowledge/digests/sector:pets", data={"body_md": "edited by founder"})
    assert r.status_code == 200 and "Saved" in r.text
    db_session.expire_all()
    assert repo.get_digest(db_session, "sector:pets") == "edited by founder"
    assert web.get("/knowledge/digests/sector:nope").status_code == 404


def test_costs_page_and_cap(web, db_session):
    from scout.clock import local_today

    day = local_today("Europe/Belgrade")
    repo.record_cost(
        db_session,
        CostRecord(
            kind="llm",
            provider="anthropic",
            model="claude-sonnet-5-5",
            units={},
            cost_eur=Decimal("0.42"),
        ),
        day=day,
        run_id=None,
    )
    r = web.get("/costs")
    assert "claude-sonnet-5-5" in r.text and "0.42" in r.text
    assert "Applies to runs started today" in r.text
    assert "07:00 Kosovo time in winter" in r.text and "manual run" in r.text
    ok = web.post("/costs/cap", data={"eur": "1.75"})
    assert ok.status_code == 200 and "1.75" in ok.text
    db_session.expire_all()
    assert founder.today_cap(db_session, day) == Decimal("1.75")
    bad = web.post("/costs/cap", data={"eur": "NaN"}, follow_redirects=False)
    assert "err=" in bad.headers["location"]


def test_settings_phase_priority_and_finalists(web, db_session):
    seed_all(db_session)
    g, _ = repo.propose_gap(db_session, title="Pet sitting", sector_slug="pets")
    founder.toggle_finalist(db_session, g.id, today=date(2026, 10, 9))
    r = web.get("/settings")
    assert "Pet sitting" in r.text and "foundation" in r.text
    web.post("/settings/phase", data={"phase": "verification"})
    db_session.expire_all()
    assert repo.get_setting(db_session, "phase") == {"value": "verification"}
    bad = web.post("/settings/phase", data={"phase": "x"}, follow_redirects=False)
    assert "err=" in bad.headers["location"]
    web.post("/settings/sector-priority", data={"slug": "pets", "priority": "99"})
    db_session.expire_all()
    assert repo.get_sector(db_session, "pets").priority == 99
    bad = web.post(
        "/settings/sector-priority",
        data={"slug": "pets", "priority": "lots"},
        follow_redirects=False,
    )
    assert "err=" in bad.headers["location"]


def test_empty_knowledge_and_settings_explain_themselves(web):
    assert "No sectors yet" in web.get("/knowledge").text
    assert "No facts match" in web.get("/knowledge", params={"q": "zzz"}).text
    settings = web.get("/settings").text
    assert "No finalists yet" in settings and "Foundation" in settings
    assert "building the knowledge base" in settings
    assert '<a href="/costs">Budget &amp; costs</a>' in settings  # section tab


def test_knowledge_cards_and_digest_editor(web, db_session):
    seed_all(db_session)
    repo.set_digest(db_session, "sector:pets", "Pets", "## Vets", now=NOW)
    html = web.get("/knowledge").text
    assert 'href="/knowledge/sectors/pets"' in html and "not mapped yet" in html
    assert "data-search" in html
    digest = web.get("/knowledge/digests/sector:pets").text
    assert 'data-open="#edit"' in digest and '<details class="card" id="edit">' in digest
    assert 'action="/knowledge/digests/sector:pets"' in digest


def test_costs_chart_cap_source_and_clear(web, db_session):
    from scout.clock import local_today

    html = web.get("/costs").text
    assert html.count('class="bar-col') == 14
    assert "Foundation phase cap" in html and "Clear my cap" not in html
    founder.set_today_cap(db_session, "1.25", today=local_today("Europe/Belgrade"))
    html = web.get("/costs").text
    assert "your cap for today" in html and "Clear my cap" in html and "€1.25" in html


def test_settings_lists_use_plain_buttons(web, db_session):
    seed_all(db_session)
    g, _ = repo.propose_gap(db_session, title="Pet sitting", sector_slug="pets")
    founder.toggle_finalist(db_session, g.id, today=date(2026, 10, 9))
    founder.flag_gap(db_session, g.id, today=date(2026, 10, 9))
    html = web.get("/settings").text
    assert "Remove" in html and "Cancel check" in html and "New idea" in html
