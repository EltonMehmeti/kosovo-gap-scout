"""Google Play signals for Kosovo (gl=XK): top-free chart ids by regex, search via gplay scraper."""

from __future__ import annotations

import re
from collections.abc import Callable

import httpx

from scout.sources.askdata import USER_AGENT
from scout.sources.types import AppHit, ChartEntry

# The legacy collection/topselling_free page no longer lists app links (checked 2026-10-09).
# The "Top charts" page server-renders the top-free list first, in rank order.
TOP_FREE_URL = "https://play.google.com/store/apps/top"
APP_ID_RE = re.compile(r"/store/apps/details\?id=([\w.]+)")
DETAILS_URL = "https://play.google.com/store/apps/details?id={app_id}"
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36 " + USER_AGENT
)


def fetch_top_free(
    country: str = "XK", limit: int = 25, http: httpx.Client | None = None
) -> list[ChartEntry]:
    client = http or httpx.Client(
        timeout=30.0, headers={"User-Agent": BROWSER_UA}, follow_redirects=True
    )
    r = client.get(TOP_FREE_URL, params={"gl": country.upper(), "hl": "en"})
    r.raise_for_status()
    ids: list[str] = []
    for m in APP_ID_RE.finditer(r.text):
        app_id = m.group(1)
        if app_id not in ids:
            ids.append(app_id)
        if len(ids) >= limit:
            break
    return [
        ChartEntry(
            rank=i + 1,
            app_key=app_id,
            name=app_id,
            publisher="",
            genres=(),
            url=f"{DETAILS_URL.format(app_id=app_id)}&gl={country.upper()}",
        )
        for i, app_id in enumerate(ids)
    ]


def _gps_search(term: str, n_hits: int, lang: str, country: str) -> list[dict]:
    from google_play_scraper import search

    return search(term, n_hits=n_hits, lang=lang, country=country)


def _gps_app(app_id: str, lang: str, country: str) -> dict:
    from google_play_scraper import app

    return app(app_id, lang=lang, country=country)


def _hit(d: dict) -> AppHit:
    app_id = d["appId"]
    return AppHit(
        store="play",
        app_key=app_id,
        name=d.get("title", ""),
        publisher=d.get("developer", ""),
        url=DETAILS_URL.format(app_id=app_id),
    )


def search_apps(
    term: str,
    country: str = "xk",
    lang: str = "sq",
    limit: int = 10,
    search_fn: Callable | None = None,
) -> list[AppHit]:
    fn = search_fn or _gps_search
    return [_hit(d) for d in fn(term, n_hits=limit, lang=lang, country=country)]


def app_details(app_id: str, country: str = "xk", app_fn: Callable | None = None) -> AppHit:
    fn = app_fn or _gps_app
    return _hit(fn(app_id, lang="en", country=country))
