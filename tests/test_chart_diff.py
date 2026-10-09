from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout.db import repo
from scout.extract.extractor import Extractor
from scout.extract.schemas import AppClassification, AppClassificationBatch
from scout.llm.gateway import LLM
from scout.sources.types import ChartEntry
from scout.worker import chart_diff as CD
from tests.fakes import FakeClient, FakeGuard, FakeMessage, text_block

pytestmark = pytest.mark.db
TODAY = date(2026, 10, 19)
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)


def _e(rank, key, name="n", publisher="p"):
    return ChartEntry(rank=rank, app_key=key, name=name, publisher=publisher, genres=(), url="u")


def _fetch(table):
    def fetch(country, limit=25, http=None):
        if country not in table:
            raise RuntimeError("down")
        return table[country]

    return fetch


APPLE = {
    "xk": [_e(1, "1", "Wolt")],
    "al": [_e(1, "1", "Wolt"), _e(2, "2", "Pawshake")],
    "mk": [_e(1, "2", "Pawshake"), _e(3, "3", "SkopjeBus")],
    "me": [_e(1, "3", "SkopjeBus")],
    "ba": [],
    "rs": [],
    "hr": [],
    "si": [],
}
PLAY = {
    "xk": [_e(1, "com.a", "A")],
    "al": [_e(1, "com.b", "B"), _e(2, "1", "Wolt")],
    "mk": [_e(1, "com.b", "B"), _e(2, "1", "Wolt")],
    "me": [],
    "ba": [],
    "rs": [],
    "hr": [],
}  # si missing


def test_chart_diff_never_mixes_stores(db_session):
    report = CD.run_chart_diff(
        db_session, TODAY, apple_fetch=_fetch(APPLE), play_fetch=_fetch(PLAY)
    )
    leads = {(lead.store, lead.app_key) for lead in report.leads}
    # apple "1" is in Kosovo, so apple "2" and "3" are leads; play "1" is NOT in Kosovo's Play chart → lead
    assert leads == {("apple", "2"), ("apple", "3"), ("play", "com.b"), ("play", "1")}
    pawshake = next(lead for lead in report.leads if lead.app_key == "2" and lead.store == "apple")
    assert sorted(pawshake.countries) == ["al", "mk"] and pawshake.best_rank == 1
    assert report.errors == ["play/si: RuntimeError: down"]
    assert report.snapshots_saved == 11  # apple 1+2+2+1+0*4=6; play 1+2+2+0*4=5 (si fetch failed)
    assert report.new_in_kosovo == []  # no earlier snapshot


def test_new_in_kosovo_and_ever_charted_suppression(db_session):
    CD.run_chart_diff(
        db_session, date(2026, 10, 12), apple_fetch=_fetch(APPLE), play_fetch=_fetch(PLAY)
    )
    apple2 = dict(APPLE)
    apple2["xk"] = [_e(1, "1", "Wolt"), _e(2, "2", "Pawshake")]  # Pawshake arrives in Kosovo
    report = CD.run_chart_diff(
        db_session, TODAY, apple_fetch=_fetch(apple2), play_fetch=_fetch(PLAY)
    )
    assert report.new_in_kosovo == ["Pawshake"]
    assert ("apple", "2") not in {(lead.store, lead.app_key) for lead in report.leads}


def test_classify_and_record_writes_sector_facts_and_skips_global_brands(db_session):
    repo.get_or_create_sector(db_session, "mobility-transit", "Mobility")
    report = CD.run_chart_diff(
        db_session, TODAY, apple_fetch=_fetch(APPLE), play_fetch=_fetch(PLAY)
    )
    batch = AppClassificationBatch(
        items=[
            AppClassification(
                app_key="3",
                category="mobility",
                consumer_need="live bus times",
                kosovo_relevance="high",
                sector_slug="mobility-transit",
                is_global_brand=False,
                note="",
            ),
            AppClassification(
                app_key="2",
                category="marketplace",
                consumer_need="pet sitting",
                kosovo_relevance="medium",
                sector_slug="pets",
                is_global_brand=False,
                note="",
            ),
            AppClassification(
                app_key="com.b",
                category="social",
                consumer_need="chat",
                kosovo_relevance="low",
                sector_slug="none",
                is_global_brand=True,
                note="",
            ),
        ]
    )
    client = FakeClient([FakeMessage(content=[text_block("{}")], parsed_output=batch)])
    extractor = Extractor(LLM(client, FakeGuard(), Decimal("0.92")))
    n = CD.classify_and_record(
        db_session,
        extractor,
        report,
        now=NOW,
        run_id=1,
        play_details=lambda app_id, country="xk": (_ for _ in ()).throw(RuntimeError()),
    )
    assert n == 2
    facts = repo.search_facts(db_session, "SkopjeBus", now=NOW)
    assert facts and facts[0].sector_id == repo.get_sector(db_session, "mobility-transit").id
    assert facts[0].value["countries"] == ["mk", "me"] and facts[0].entity_type == "stat"
    assert "SkopjeBus" in client.messages.calls[0]["messages"][0]["content"]


def test_no_leads_means_no_model_call(db_session):
    same = {c: [_e(1, "1", "Wolt")] for c in CD.CHART_COUNTRIES}
    report = CD.run_chart_diff(db_session, TODAY, apple_fetch=_fetch(same), play_fetch=_fetch(same))
    client = FakeClient([])
    assert (
        CD.classify_and_record(
            db_session,
            Extractor(LLM(client, FakeGuard(), Decimal("0.92"))),
            report,
            now=NOW,
            run_id=1,
        )
        == 0
    )
    assert client.messages.calls == []


def test_same_app_key_in_both_stores_stays_separate(db_session):
    apple = {c: [] for c in CD.CHART_COUNTRIES}
    play = {c: [] for c in CD.CHART_COUNTRIES}
    apple["xk"] = [_e(1, "42", "AppleKnown")]  # apple 42 is in Kosovo
    play["al"] = [_e(1, "42", "PlayOnly")]
    play["mk"] = [_e(2, "42", "PlayOnly")]
    play["xk"] = [_e(1, "other", "Other")]
    apple["al"] = [_e(1, "42", "AppleKnown")]
    apple["mk"] = [_e(1, "42", "AppleKnown")]
    report = CD.run_chart_diff(
        db_session, TODAY, apple_fetch=_fetch(apple), play_fetch=_fetch(play)
    )
    assert [(lead.store, lead.app_key) for lead in report.leads] == [("play", "42")]
    assert report.leads[0].name == "PlayOnly" and report.leads[0].countries == ["al", "mk"]
