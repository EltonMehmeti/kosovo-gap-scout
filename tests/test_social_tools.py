from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout.budget.guard import BudgetGuard
from scout.db import repo
from scout.db.models import Ad, Cost, Fact, Source
from scout.seeds import seed_all
from scout.sources.apify import ActorResult, ApifyError
from scout.sources.askdata import AskDataClient
from scout.sources.crawl import CrawlRefused
from scout.worker import tools as T
from tests.social_samples import ADS, PROFILES

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
DAY = date(2026, 10, 19)


class FakeApify:
    def __init__(self, items=None, cost="0.05", error=None):
        self.items, self.cost, self.error = items or [], cost, error
        self.calls = []

    def run(self, actor, actor_input, *, max_items):
        self.calls.append((actor, actor_input, max_items))
        if self.error:
            raise self.error
        return ActorResult(items=list(self.items), cost_usd=Decimal(self.cost), run_id="r1")


class FakeCrawler:
    def __init__(self, error=None):
        self.error, self.urls = error, []

    def fetch(self, url):
        self.urls.append(url)
        if self.error:
            raise self.error
        return "# listings\n- torta 25€"


@pytest.fixture
def gap(db_session):
    seed_all(db_session)
    g, _ = repo.propose_gap(db_session, title="Cake delivery", sector_slug="pets")
    g.score_total = 72
    db_session.commit()
    return g


def _ctx(session, *, gap=None, profile="verify-gap", apify=None, crawler=None, day=DAY):
    run = repo.start_run(
        session, day=day, phase="foundation", budget_cap_eur=Decimal("3"), started_at=NOW
    )
    payload = {"gap_id": gap.id, "sector": "pets"} if gap is not None else {}
    return T.ToolContext(
        session=session,
        guard=BudgetGuard(session, day=day, daily_cap_eur=Decimal("3"), run_id=run.id),
        now=NOW,
        run_id=run.id,
        task_id=None,
        places=None,
        askdata=AskDataClient(),
        profile=profile,
        payload=payload,
        apify=apify,
        crawler=crawler,
    )


def _apify_costs(session):
    return session.query(Cost).filter_by(kind="apify").all()


def test_instagram_search_records_shops_fact_and_free_credit_cost(db_session, gap):
    fake = FakeApify(PROFILES)
    ctx = _ctx(db_session, gap=gap, apify=fake)
    out = T.instagram_search_impl(ctx, query="torta prishtine")
    assert "@tortat.e.mira" in out and "price 1" in out and "ana.private" not in out
    assert fake.calls[0][2] == 30 and fake.calls[0][1]["searchType"] == "user"
    fact = db_session.query(Fact).filter_by(entity_type="social", entity_key=f"gap:{gap.id}").one()
    assert fact.value["shops"][0]["username"] == "tortat.e.mira"
    (cost,) = _apify_costs(db_session)
    assert cost.units["usd"] == "0.05" and cost.cost_eur == 0
    src = db_session.query(Source).filter_by(name="apify-instagram").one()
    assert src.enabled is True and src.last_ok_at is not None
    assert ctx.social_ok == 1


def test_score_below_60_is_refused_without_a_call(db_session, gap):
    gap.score_total = 40
    db_session.commit()
    fake = FakeApify(PROFILES)
    out = T.instagram_search_impl(_ctx(db_session, gap=gap, apify=fake), query="torta")
    assert out.startswith("paid social checks run only") and fake.calls == []


def test_flagged_gap_below_60_is_allowed(db_session, gap):
    gap.score_total = 40
    repo.set_setting(db_session, "flagged_gaps", [gap.id])
    db_session.commit()
    fake = FakeApify(PROFILES)
    T.instagram_search_impl(_ctx(db_session, gap=gap, apify=fake), query="torta")
    assert len(fake.calls) == 1


def test_other_profiles_are_refused(db_session, gap):
    fake = FakeApify(ADS)
    ctx = _ctx(db_session, gap=gap, profile="map-sector", apify=fake)
    assert T.ad_library_search_impl(ctx, query="torta").startswith("paid social checks")
    assert fake.calls == []


def test_second_paid_call_in_a_task_is_refused(db_session, gap):
    fake = FakeApify(PROFILES)
    ctx = _ctx(db_session, gap=gap, apify=fake)
    T.instagram_search_impl(ctx, query="torta")
    assert T.instagram_search_impl(ctx, query="kek").startswith("error: one instagram_search")
    assert len(fake.calls) == 1


def test_cache_hit_is_free_and_does_not_count(db_session, gap):
    fake = FakeApify(PROFILES)
    T.instagram_search_impl(_ctx(db_session, gap=gap, apify=fake), query="Torta  Prishtine")
    ctx2 = _ctx(db_session, gap=gap, apify=fake)
    assert "@tortat.e.mira" in T.instagram_search_impl(ctx2, query="torta prishtine")
    assert len(fake.calls) == 1 and len(_apify_costs(db_session)) == 1
    T.instagram_search_impl(ctx2, query="kek")
    assert len(fake.calls) == 2


def test_long_query_works_and_empty_query_is_refused(db_session, gap):
    fake = FakeApify(PROFILES)
    ctx = _ctx(db_session, gap=gap, apify=fake)
    assert T.instagram_search_impl(ctx, query="   ").startswith("error: query is empty")
    assert "@tortat.e.mira" in T.instagram_search_impl(ctx, query="torta " * 100)


def test_monthly_cap_blocks_and_resets_next_month(db_session, gap):
    repo.record_cost(
        db_session,
        repo.CostRecord("apify", "apify", "ads", {"usd": "4.50"}, Decimal("0")),
        day=date(2026, 10, 5),
        run_id=None,
    )
    fake = FakeApify(PROFILES)
    out = T.instagram_search_impl(_ctx(db_session, gap=gap, apify=fake), query="torta")
    assert out == (
        "social source unavailable: Social credit used up for October — paid social checks "
        "resume Nov 1."
    )
    assert fake.calls == []
    next_month = _ctx(db_session, gap=gap, apify=fake, day=date(2026, 11, 1))
    T.instagram_search_impl(next_month, query="kek")
    assert len(fake.calls) == 1


def test_failed_run_records_its_cost_and_makes_the_presence_check_partial(db_session, gap):
    fake = FakeApify(error=ApifyError("run failed", Decimal("0.02")))
    ctx = _ctx(db_session, gap=gap, apify=fake)
    assert T.instagram_search_impl(ctx, query="torta") == "social source unavailable: run failed"
    assert [c.units["usd"] for c in _apify_costs(db_session)] == ["0.02"]
    assert db_session.query(Source).filter_by(name="apify-instagram").one().failure_count == 1
    ctx.places_searches, ctx.app_store_searches = 7, 1
    T.kb_record_fact_impl(
        ctx,
        claim="presence check: absent",
        entity_type="presence_check",
        entity_key=f"gap:{gap.id}",
        confidence=0.8,
        value_json='{"verdict": "absent"}',
    )
    fact = db_session.query(Fact).filter_by(entity_type="presence_check").one()
    assert fact.value["social"] == "partial" and fact.value["verdict"] == "absent"
    assert fact.confidence == 0.5


def test_presence_check_is_not_partial_after_a_social_result(db_session, gap):
    ctx = _ctx(db_session, gap=gap, apify=FakeApify(PROFILES))
    T.instagram_search_impl(ctx, query="torta")
    ctx.places_searches, ctx.app_store_searches = 7, 1
    T.kb_record_fact_impl(
        ctx,
        claim="presence check: instagram-only",
        entity_type="presence_check",
        entity_key=f"gap:{gap.id}",
        confidence=0.8,
        value_json='{"verdict": "instagram-only"}',
    )
    fact = db_session.query(Fact).filter_by(entity_type="presence_check").one()
    assert "social" not in fact.value and fact.value["verdict"] == "instagram-only"
    assert fact.confidence == 0.8


def test_ad_library_search_stores_ads_and_a_signal_fact(db_session, gap):
    fake = FakeApify(ADS)
    out = T.ad_library_search_impl(_ctx(db_session, gap=gap, apify=fake), query="torta")
    assert "3 Meta ads" in out and "1 foreign" in out and fake.calls[0][2] == 50
    assert "q=torta" in fake.calls[0][1]["startUrls"][0]["url"]
    assert {a.ad_archive_id for a in repo.ads_for_gap(db_session, gap.id)} == {"111", "222", "333"}
    fact = db_session.query(Fact).filter_by(entity_type="ad_signal").one()
    assert fact.value["count"] == 3


def test_oversized_results_are_cut_to_the_limit(db_session, gap):
    many = [ADS[0] | {"adArchiveID": str(n)} for n in range(80)]
    T.ad_library_search_impl(_ctx(db_session, gap=gap, apify=FakeApify(many)), query="torta")
    assert db_session.query(Ad).count() == 50


def test_ads_sweep_gets_300_ads_and_no_instagram(db_session):
    seed_all(db_session)
    fake = FakeApify(ADS)
    ctx = _ctx(db_session, profile="ads-sweep", apify=fake)
    assert T.instagram_search_impl(ctx, query="torta").startswith("error: the weekly ads sweep")
    out = T.ad_library_search_impl(ctx, query="")
    assert out.startswith("3 Meta ads") and fake.calls[0][2] == 300
    assert db_session.query(Ad).filter(Ad.gap_id.is_(None)).count() == 3
    assert db_session.query(Fact).filter_by(entity_type="ad_signal").count() == 0


def test_crawl_tool_allowlist_cap_and_failures(db_session):
    seed_all(db_session)
    crawler = FakeCrawler()
    ctx = _ctx(db_session, crawler=crawler)
    assert T.kosovo_site_crawl_impl(ctx, url="https://instagram.com/x").startswith("error: only")
    for n in range(20):
        assert T.kosovo_site_crawl_impl(ctx, url=f"https://www.merrjep.com/{n}").startswith(
            "# list"
        )
    assert T.kosovo_site_crawl_impl(ctx, url="https://www.merrjep.com/21").startswith("crawl limit")
    assert len(crawler.urls) == 20
    for error in (CrawlRefused("robots.txt disallows this page"), RuntimeError("render died")):
        ctx2 = _ctx(db_session, crawler=FakeCrawler(error=error))
        assert T.kosovo_site_crawl_impl(ctx2, url="https://koha.net/a").startswith("page skipped")
    assert db_session.query(Source).filter_by(name="kosovo-sites").one().failure_count == 2


def test_tools_are_offered_only_when_configured(db_session, gap):
    plain = T.build_tools(_ctx(db_session, gap=gap))
    assert [t.name for t in plain] == list(T.TOOL_NAMES)
    full = T.build_tools(_ctx(db_session, gap=gap, apify=FakeApify(), crawler=FakeCrawler()))
    assert [t.name for t in full] == [*T.TOOL_NAMES, *T.SOCIAL_TOOL_NAMES, *T.CRAWL_TOOL_NAMES]
    assert T.instagram_search_impl(_ctx(db_session, gap=gap), query="x").startswith(
        "instagram_search unavailable"
    )


def test_ads_sweep_skips_the_cache_and_lists_advertisers(db_session):
    seed_all(db_session)
    fake = FakeApify([ADS[0] | {"adArchiveID": str(n)} for n in range(5)])
    T.ad_library_search_impl(_ctx(db_session, profile="ads-sweep", apify=fake), query="")
    out = T.ad_library_search_impl(_ctx(db_session, profile="ads-sweep", apify=fake), query="")
    assert len(fake.calls) == 2
    assert out.splitlines()[1].startswith("- Torta Shop | 5 ads |")


def test_instagram_questions_line_comes_before_the_shops(db_session, gap):
    many = [PROFILES[0] | {"username": f"shop{n}"} for n in range(30)]
    out = T.instagram_search_impl(_ctx(db_session, gap=gap, apify=FakeApify(many)), query="torta")
    assert out.splitlines()[1].startswith("comment questions:")
