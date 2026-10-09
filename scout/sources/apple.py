"""Apple App Store signals: top-free charts (RSS, 8 countries) and keyword presence checks."""

from __future__ import annotations

import httpx

from scout.sources.askdata import USER_AGENT
from scout.sources.types import AppHit, ChartEntry

RSS_URL = "https://rss.marketingtools.apple.com/api/v2/{country}/apps/top-free/{limit}/apps.json"
SEARCH_URL = "https://itunes.apple.com/search"


def _http(http: httpx.Client | None) -> httpx.Client:
    return http or httpx.Client(
        timeout=30.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    )


def fetch_top_free(
    country: str, limit: int = 25, http: httpx.Client | None = None
) -> list[ChartEntry]:
    r = _http(http).get(RSS_URL.format(country=country.lower(), limit=limit))
    r.raise_for_status()
    results = r.json().get("feed", {}).get("results", [])
    return [
        ChartEntry(
            rank=i + 1,
            app_key=str(a["id"]),
            name=a.get("name", ""),
            publisher=a.get("artistName", ""),
            genres=tuple(g.get("name", "") for g in a.get("genres", [])),
            url=a.get("url", ""),
        )
        for i, a in enumerate(results)
    ]


def search_apps(
    term: str, country: str = "xk", limit: int = 10, http: httpx.Client | None = None
) -> list[AppHit]:
    r = _http(http).get(
        SEARCH_URL, params={"term": term, "country": country, "entity": "software", "limit": limit}
    )
    r.raise_for_status()
    return [
        AppHit(
            store="apple",
            app_key=str(a["trackId"]),
            name=a.get("trackName", ""),
            publisher=a.get("sellerName", ""),
            url=a.get("trackViewUrl", ""),
        )
        for a in r.json().get("results", [])
    ]
