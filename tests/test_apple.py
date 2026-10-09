import httpx
import pytest

from scout.sources import apple


def test_fetch_top_free_maps_rss_feed():
    def handler(request):
        assert (
            str(request.url)
            == "https://rss.marketingtools.apple.com/api/v2/xk/apps/top-free/25/apps.json"
        )
        return httpx.Response(
            200,
            json={
                "feed": {
                    "results": [
                        {
                            "id": "1",
                            "name": "Wolt",
                            "artistName": "Wolt Enterprises",
                            "genres": [{"name": "Food & Drink"}],
                            "url": "https://apps.apple.com/xk/app/wolt/id1",
                        },
                        {
                            "id": "2",
                            "name": "APTV",
                            "artistName": "Artmotion",
                            "genres": [],
                            "url": "u2",
                        },
                    ]
                }
            },
        )

    entries = apple.fetch_top_free("XK", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert [(e.rank, e.app_key, e.name) for e in entries] == [(1, "1", "Wolt"), (2, "2", "APTV")]
    assert entries[0].genres == ("Food & Drink",) and entries[0].publisher == "Wolt Enterprises"


def test_search_apps_uses_country_and_software_entity():
    def handler(request):
        assert request.url.params["country"] == "xk" and request.url.params["entity"] == "software"
        assert request.url.params["term"] == "dentist booking"
        return httpx.Response(
            200,
            json={
                "resultCount": 1,
                "results": [
                    {
                        "trackId": 99,
                        "trackName": "DentApp",
                        "sellerName": "X",
                        "trackViewUrl": "https://a",
                    }
                ],
            },
        )

    hits = apple.search_apps(
        "dentist booking", http=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert hits == [
        apple.AppHit(store="apple", app_key="99", name="DentApp", publisher="X", url="https://a")
    ]


@pytest.mark.network
def test_live_xk_chart_has_entries():
    assert len(apple.fetch_top_free("xk", limit=10)) >= 5
