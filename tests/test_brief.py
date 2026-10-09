from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import anthropic
import httpx
import pytest

from scout.db import repo
from scout.db.repo import CostRecord, FactIn
from scout.editor import brief as B
from scout.llm.gateway import LLM
from scout.strategy.strategist import GapChange
from tests.fakes import FakeClient, FakeGuard, FakeMessage, text_block

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 19, 6, 40, tzinfo=UTC)
TODAY = date(2026, 10, 19)


@pytest.fixture
def run(db_session):
    r = repo.start_run(
        db_session,
        day=TODAY,
        phase="foundation",
        budget_cap_eur=Decimal("3"),
        started_at=NOW - timedelta(minutes=40),
    )
    t = repo.enqueue_task(db_session, profile="map-sector", payload={"sector": "pets"}, run_id=r.id)
    repo.claim_next_task(db_session, "w", now=NOW)
    repo.finish_task(db_session, t, result_md="ok", actual_cost_eur=Decimal("0.31"), now=NOW)
    repo.record_cost(
        db_session,
        CostRecord("llm", "anthropic", "claude-sonnet-5-5", {}, Decimal("0.31")),
        day=TODAY,
        run_id=r.id,
    )
    return r


def test_quiet_day_single_line_and_no_model_call(db_session, run):
    client = FakeClient([])
    md = B.write_brief(
        db_session, LLM(client, FakeGuard(), Decimal("0.92")), run, today=TODAY, now=NOW, changes=[]
    )
    assert md == "Quiet day — 1 tasks, €0.31, nothing moved."
    assert client.messages.calls == [] and repo.latest_brief(db_session).markdown == md


def test_busy_day_has_all_sections_and_narrative(db_session, run):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    gap, _ = repo.propose_gap(db_session, title="Pet sitting marketplace", sector_slug="pets")
    repo.upsert_fact(
        db_session,
        FactIn(
            claim="Prizren has 3 pet shops",
            entity_type="sector",
            entity_key="pets",
            confidence=0.7,
            sector_slug="pets",
            source_url="https://x",
        ),
        run_id=run.id,
        observed_at=NOW - timedelta(minutes=10),
    )
    repo.add_field_check(
        db_session,
        gap_id=gap.id,
        question="Any sitters in Prizren?",
        why="low confidence",
        due=TODAY + timedelta(days=7),
    )
    changes = [
        GapChange(
            gap.id, "Pet sitting marketplace", "candidate", "verifying", 0, 64, 0.5, "strong proof"
        )
    ]
    client = FakeClient(
        [FakeMessage(content=[text_block("Today the scout found a promising pet gap.")])]
    )
    md = B.write_brief(
        db_session,
        LLM(client, FakeGuard(), Decimal("0.92")),
        run,
        today=TODAY,
        now=NOW,
        changes=changes,
    )
    for heading in (
        "## What changed",
        "## Field checks for you",
        "## What the scout did",
        "## What it learned",
        "## Source health",
        "## Spend",
    ):
        assert heading in md
    assert "Pet sitting marketplace" in md and "candidate → verifying" in md and "64" in md
    assert (
        "Any sitters in Prizren?" in md and "Prizren has 3 pet shops" in md and "<https://x>" in md
    )
    assert "€0.31" in md and "cap €3.00" in md
    assert md.splitlines()[0].startswith("# ") and "promising pet gap" in md
    kw = client.messages.calls[0]
    assert kw["model"] == "claude-sonnet-5-5" and kw["output_config"] == {"effort": "low"}


def test_narrative_failure_is_tolerated(db_session, run):
    repo.upsert_fact(
        db_session,
        FactIn(claim="Something important", entity_type="news", entity_key="k", confidence=0.9),
        run_id=run.id,
        observed_at=NOW,
    )
    client = FakeClient([FakeMessage(content=[], stop_reason="refusal")])
    md = B.write_brief(
        db_session, LLM(client, FakeGuard(), Decimal("0.92")), run, today=TODAY, now=NOW, changes=[]
    )
    assert "Something important" in md and "## What it learned" in md
    assert repo.latest_brief(db_session).markdown == md


def test_api_error_still_saves_brief(db_session, run):
    repo.upsert_fact(
        db_session,
        FactIn(claim="Something important", entity_type="news", entity_key="k", confidence=0.9),
        run_id=run.id,
        observed_at=NOW,
    )
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
    client = FakeClient([err])
    md = B.write_brief(
        db_session, LLM(client, FakeGuard(), Decimal("0.92")), run, today=TODAY, now=NOW, changes=[]
    )
    assert "Something important" in md
    assert repo.latest_brief(db_session).markdown == md


def test_spend_reflects_narrative_cost(db_session, run):
    repo.upsert_fact(
        db_session,
        FactIn(claim="Something important", entity_type="news", entity_key="k", confidence=0.9),
        run_id=run.id,
        observed_at=NOW,
    )
    client = FakeClient([FakeMessage(content=[text_block("Opening.")])])
    orig = client.messages.create

    def create(**kw):
        repo.record_cost(
            db_session,
            CostRecord("llm", "anthropic", "claude-sonnet-5-5", {}, Decimal("0.40")),
            day=TODAY,
            run_id=run.id,
        )
        return orig(**kw)

    client.messages.create = create
    md = B.write_brief(
        db_session, LLM(client, FakeGuard(), Decimal("0.92")), run, today=TODAY, now=NOW, changes=[]
    )
    assert "today €0.71" in md and "month to date €0.71" in md


def _quiet_inputs(statuses, chart_errors=()):
    from types import SimpleNamespace

    return B.BriefInputs(
        run=None,
        today=TODAY,
        changes=[],
        fresh_facts=[],
        field_checks=[],
        tasks=[SimpleNamespace(status=s) for s in statuses],
        chart_errors=list(chart_errors),
        spent_today=Decimal("0.4"),
        spent_mtd=Decimal("1"),
        cap=Decimal("3"),
        places_calls=0,
    )


def test_quiet_day_line_reports_failures_and_chart_errors():
    assert B.render_brief(_quiet_inputs(["done", "done"])) == (
        "Quiet day — 2 tasks, €0.40, nothing moved."
    )
    assert B.render_brief(_quiet_inputs(["failed"] * 5)) == (
        "Quiet day — 5 tasks, €0.40, nothing moved; 5 failed."
    )
    assert B.render_brief(_quiet_inputs(["done", "failed"], ["xk apple: timeout"])) == (
        "Quiet day — 2 tasks, €0.40, nothing moved; 1 failed; 1 chart errors."
    )
