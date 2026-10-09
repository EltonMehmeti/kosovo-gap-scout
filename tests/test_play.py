import httpx
import pytest

from scout.sources import play

HTML = """
<a href="/store/apps/details?id=com.wolt.android&gl=XK">Wolt</a>
<a href="/store/apps/details?id=com.wolt.android">Wolt again</a>
<a href="/store/apps/details?id=al.gjirafa.mall">GjirafaMall</a>
<a href="/store/apps/details?id=com.aptv.app">APTV</a>
"""


def test_fetch_top_free_dedupes_and_limits():
    def handler(request):
        assert request.url.params["gl"] == "XK"
        return httpx.Response(200, text=HTML)

    entries = play.fetch_top_free(
        "xk", limit=2, http=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert [(e.rank, e.app_key) for e in entries] == [
        (1, "com.wolt.android"),
        (2, "al.gjirafa.mall"),
    ]
    assert entries[0].url.endswith("details?id=com.wolt.android&gl=XK")


def test_regex_matches_dotted_ids_only():
    assert play.APP_ID_RE.findall("x /store/apps/details?id=com.a_b.c9&hl=en y") == ["com.a_b.c9"]


def test_search_apps_wraps_google_play_scraper():
    calls = {}

    def fake_search(term, n_hits, lang, country):
        calls.update(term=term, n_hits=n_hits, lang=lang, country=country)
        return [{"appId": "com.x", "title": "X", "developer": "Dev"}]

    hits = play.search_apps("dentist", search_fn=fake_search)
    assert calls == {"term": "dentist", "n_hits": 10, "lang": "sq", "country": "xk"}
    assert hits[0] == play.AppHit(
        store="play",
        app_key="com.x",
        name="X",
        publisher="Dev",
        url="https://play.google.com/store/apps/details?id=com.x",
    )


def test_app_details_wraps_app_lookup():
    hit = play.app_details(
        "com.x",
        app_fn=lambda app_id, lang, country: {"appId": app_id, "title": "X", "developer": "D"},
    )
    assert hit.name == "X" and hit.store == "play"


@pytest.mark.network
def test_live_play_search_kosovo():
    assert play.search_apps("taxi", limit=3)
