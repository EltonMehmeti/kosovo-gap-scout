import json
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from scout.budget.guard import BudgetGuard
from scout.db import repo
from scout.sources.askdata import AskDataClient
from scout.sources.places import PlacesClient
from scout.sources.types import AppHit
from scout.worker import tools as T

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
DAY = date(2026, 10, 19)


def _places_http():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "places": [
                    {
                        "id": "p1",
                        "displayName": {"text": "Vet Prizren"},
                        "formattedAddress": "Prizren",
                        "primaryType": "veterinary_care",
                        "businessStatus": "OPERATIONAL",
                    }
                ]
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def _askdata_http():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "columns": [{"code": "Y", "text": "Year"}],
                    "data": [{"key": ["2024"], "values": ["1"]}],
                },
            )
        if request.url.path.endswith(".px"):
            return httpx.Response(
                200,
                json={
                    "title": "T",
                    "variables": [
                        {"code": "Y", "text": "Year", "values": ["2024"], "valueTexts": ["2024"]}
                    ],
                },
            )
        return httpx.Response(200, json=[{"id": "Population", "type": "l", "text": "Population"}])

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def ctx(db_session):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    run = repo.start_run(
        db_session, day=DAY, phase="foundation", budget_cap_eur=Decimal("3"), started_at=NOW
    )
    guard = BudgetGuard(db_session, day=DAY, daily_cap_eur=Decimal("3"), run_id=run.id)
    return T.ToolContext(
        session=db_session,
        guard=guard,
        now=NOW,
        run_id=run.id,
        task_id=None,
        places=PlacesClient("k", http=_places_http()),
        askdata=AskDataClient(http=_askdata_http()),
        apple_search=lambda term, country, limit: [
            AppHit("apple", "1", "PetApp", "X", "https://a")
        ],
        play_search=lambda term, country, lang, limit: [],
    )


def test_record_fact_then_search_returns_it_with_digest(ctx):
    out = T.kb_record_fact_impl(
        ctx,
        claim="Prizren has 3 pet shops",
        entity_type="sector",
        entity_key="pets",
        confidence=0.7,
        source_url="https://x",
        sector="pets",
        ttl_days=30,
        value_json='{"count": 3}',
    )
    assert out.startswith("fact #")
    T.kb_write_digest_impl(
        ctx, key="sector:pets", title="Pets", body_md="# Pets\nSmall but growing."
    )
    res = T.kb_search_impl(ctx, query="pet shops Prizren", sector="pets")
    assert "DIGEST:" in res and "[0.70] Prizren has 3 pet shops" in res and "<https://x>" in res
    assert len(res) <= T.KB_RESULT_LIMIT


def test_record_fact_rejects_bad_entity_type_and_clamps_confidence(ctx):
    assert T.kb_record_fact_impl(
        ctx, claim="x", entity_type="rumour", entity_key="k", confidence=0.5
    ).startswith("error:")
    T.kb_record_fact_impl(ctx, claim="y", entity_type="culture", entity_key="k", confidence=7)
    assert repo.search_facts(ctx.session, "y", now=NOW)[0].confidence == 1.0


def test_business_model_gap_tools(ctx):
    assert T.kb_record_business_impl(
        ctx, name="PetShop KS", sector="pets", city="Prishtinë", instagram="petshopks"
    ).startswith("business #")
    assert repo.list_businesses(ctx.session, "pets")[0].channels == {"instagram": "petshopks"}
    out = T.kb_record_proven_model_impl(
        ctx,
        slug="pet-sitting-marketplace",
        name="Pet sitting marketplace",
        sector="pets",
        description="Rover-style",
        markets_json=json.dumps([{"country": "HR", "example": "Pawshake", "url": "u"}]),
    )
    assert "nearby markets: 1" in out
    first = T.kb_propose_gap_impl(
        ctx,
        title="Pet sitting marketplace",
        sector="pets",
        hypothesis="h",
        presence_level="unknown",
        proven_model_slug="pet-sitting-marketplace",
    )
    again = T.kb_propose_gap_impl(
        ctx, title="pet sitting MARKETPLACE", sector="pets", hypothesis="h2"
    )
    assert "(new)" in first and "(existing)" in again
    assert T.kb_propose_gap_impl(
        ctx, title="x", sector="pets", hypothesis="h", presence_level="maybe"
    ).startswith("error:")


def test_write_digest_validates_key_and_length(ctx):
    assert T.kb_write_digest_impl(ctx, key="random", title="t", body_md="b").startswith("error:")
    long_body = "x" * 6000
    T.kb_write_digest_impl(ctx, key="culture:payments-and-trust", title="t", body_md=long_body)
    assert len(repo.get_digest(ctx.session, "culture:payments-and-trust")) == T.DIGEST_CHAR_LIMIT


def test_places_search_records_cost_and_respects_quota(ctx):
    out = T.places_search_impl(ctx, query="veteriner", city="Prizren")
    assert "Vet Prizren" in out and "veterinary_care" in out
    assert repo.places_calls_in_month(ctx.session, DAY) == 1
    ctx.places_monthly_quota = 1
    assert "quota" in T.places_search_impl(ctx, query="veteriner", city="Pejë")
    ctx.places = None
    assert "unavailable" in T.places_search_impl(ctx, query="x")


def test_app_store_search_merges_stores_and_survives_errors(ctx):
    out = T.app_store_search_impl(ctx, term="pet", store="both")
    assert "[apple] PetApp" in out and "play: 0 results" in out

    def boom(term, country, limit):
        raise RuntimeError("down")

    ctx.apple_search = boom
    assert "apple: error" in T.app_store_search_impl(ctx, term="pet", store="apple")


def test_askdata_tools(ctx):
    assert "Population" in T.askdata_list_impl(ctx, path="")
    assert "Year" in T.askdata_table_impl(ctx, path="Population/t.px")
    out = T.askdata_fetch_impl(ctx, path="Population/t.px", selections_json='{"Y": ["2024"]}')
    assert "2024" in out and "1" in out
    assert T.askdata_fetch_impl(ctx, path="Population/t.px", selections_json="not json").startswith(
        "error:"
    )


def test_build_tools_names_and_schemas(ctx):
    tools = T.build_tools(ctx)
    assert [t.name for t in tools] == list(T.TOOL_NAMES)
    schema = next(t for t in tools if t.name == "kb_record_fact").to_dict()["input_schema"]
    assert set(schema["required"]) >= {"claim", "entity_type", "entity_key", "confidence"}
    assert (
        tools[0].call({"query": "pet", "sector": "pets"}).startswith(("DIGEST", "no facts", "- ["))
    )
    assert len(ctx.events) == 1 and ctx.events[0]["tool"] == "kb_search"


VALID_INPUTS = {
    "kb_search": {"query": "pet shops", "sector": "pets"},
    "kb_record_fact": {
        "claim": "Prizren has 3 pet shops",
        "entity_type": "sector",
        "entity_key": "pets",
        "confidence": 0.7,
        "source_url": "https://x",
        "sector": "pets",
        "ttl_days": 30,
        "value_json": '{"count": 3}',
    },
    "kb_record_business": {
        "name": "PetShop KS",
        "sector": "pets",
        "kind": "local",
        "city": "Prishtinë",
        "instagram": "petshopks",
        "website": "https://petshop.example",
        "facebook": "",
        "note": "food and toys, cash on delivery",
    },
    "kb_record_proven_model": {
        "slug": "pet-sitting-marketplace",
        "name": "Pet sitting marketplace",
        "sector": "pets",
        "description": "Rover-style marketplace.",
        "markets_json": json.dumps([{"country": "HR", "example": "Pawshake", "url": "https://p"}]),
        "business_model": "commission",
        "source_urls_json": json.dumps(["https://p"]),
    },
    "kb_propose_gap": {
        "title": "Pet sitting marketplace",
        "sector": "pets",
        "hypothesis": "Diaspora families pay for sitters in summer.",
        "presence_level": "unknown",
        "proven_model_slug": "pet-sitting-marketplace",
        "why_not_yet": "trust",
    },
    "kb_write_digest": {"key": "sector:pets", "title": "Pets", "body_md": "# Pets"},
    "places_search": {"query": "veteriner", "city": "Prizren", "language": "sq"},
    "app_store_search": {"term": "pet", "store": "both"},
    "askdata_list": {"path": ""},
    "askdata_table": {"path": "Population/t.px"},
    "askdata_fetch": {"path": "Population/t.px", "selections_json": '{"Y": ["2024"]}'},
}


def test_every_built_tool_succeeds_through_its_real_call_path(ctx):
    """Each tool object the runner sees, invoked via .call() exactly as the SDK runner does."""
    tools = T.build_tools(ctx)
    assert set(VALID_INPUTS) == set(T.TOOL_NAMES) == {t.name for t in tools}
    for tool in tools:
        out = tool.call(VALID_INPUTS[tool.name])
        assert isinstance(out, str) and out, tool.name
        assert not out.lower().startswith("error"), f"{tool.name}: {out}"
    assert [e["tool"] for e in ctx.events] == list(T.TOOL_NAMES)
    assert not any(e["error"] for e in ctx.events)
    assert repo.list_businesses(ctx.session, "pets")[0].name == "PetShop KS"
    gap = repo.get_gap_by_title(ctx.session, "pets", "Pet sitting marketplace")
    assert gap is not None and gap.proven_model_id is not None


def test_db_error_in_a_tool_rolls_back_so_cost_records_still_work(ctx, monkeypatch):
    from sqlalchemy import text

    from scout.db.repo import CostRecord

    def broken_upsert(session, **kwargs):
        session.execute(text("SELECT 1/0"))  # a real Postgres error: the transaction is aborted

    monkeypatch.setattr(T.repo, "upsert_business", broken_upsert)
    tool = next(t for t in T.build_tools(ctx) if t.name == "kb_record_business")
    out = tool.call({"name": "PetShop KS", "sector": "pets"})
    assert out.startswith("error: DataError")
    # the session must be usable again: the next paid message is recorded and tools keep working
    ctx.guard.record(
        CostRecord("llm", "anthropic", "claude-sonnet-5-5", {}, Decimal("0.02"), task_id=None)
    )
    assert repo.spent_on(ctx.session, DAY) == Decimal("0.020000")
    assert T.kb_search_impl(ctx, query="pets") == "no facts yet"


def test_model_strings_are_fitted_to_column_widths(ctx):
    out = T.kb_record_business_impl(
        ctx, name="N" * 300, sector="pets", kind="local (Instagram-only)", city="C" * 200
    )
    assert out.startswith("business #")
    b = repo.list_businesses(ctx.session, "pets")[0]
    assert b.kind == "local" and len(b.name) == 200 and len(b.city) == 80
    assert T.kb_record_business_impl(ctx, name="X", sector="pets", kind="cousin").startswith(
        "error: kind must be one of"
    )
    assert T.kb_record_business_impl(ctx, name="Y", sector="pets", kind="Neighbour").startswith(
        "business #"
    )
    assert repo.list_businesses(ctx.session, "pets")[-1].kind == "nearby"
    assert T.kb_propose_gap_impl(ctx, title="T" * 400, sector="pets", hypothesis="h").startswith(
        "gap #"
    )
    assert T.kb_record_fact_impl(
        ctx, claim="c", entity_type="stat", entity_key="k" * 400, confidence=0.5
    ).startswith("fact #")
    assert T.kb_record_proven_model_impl(
        ctx,
        slug="s" * 300,
        name="M" * 300,
        sector="pets",
        description="d",
        markets_json='[{"country": "HR"}]',
    ).startswith("proven model")
    assert T.kb_write_digest_impl(
        ctx, key="culture:" + "x" * 200, title="t" * 300, body_md="b"
    ).startswith("digest")
