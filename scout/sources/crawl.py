"""Polite fetches of allowlisted Kosovo sites, rendered to Markdown by Crawl4AI (optional extra `crawl`)."""

from __future__ import annotations

import importlib.util
import time
from collections.abc import Callable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

ALLOWED_DOMAINS = (
    "merrjep.com",
    "gjirafa50.com",
    "kosovajob.com",
    "telegrafi.com",
    "koha.net",
    "kallxo.com",
    "prishtinainsight.com",
    "arbk.rks-gov.net",
)
SOURCE_BY_DOMAIN = {"merrjep.com": "merrjep", "kosovajob.com": "kosovajob"}
DEFAULT_SOURCE = "kosovo-sites"
MIN_INTERVAL_S = 2.0
USER_AGENT = "KosovoGapScout/1.0 (+https://github.com/EltonMehmeti/kosovo-gap-scout)"


class CrawlRefused(RuntimeError):
    pass


def crawl_available() -> bool:
    return importlib.util.find_spec("crawl4ai") is not None


def allowed_domain(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    for domain in ALLOWED_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return domain
    return None


def source_for(domain: str) -> str:
    return SOURCE_BY_DOMAIN.get(domain, DEFAULT_SOURCE)


def _render_with_crawl4ai(url: str) -> str:
    import asyncio

    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    async def go() -> str:
        async with AsyncWebCrawler(
            config=BrowserConfig(headless=True, user_agent=USER_AGENT)
        ) as crawler:
            res = await crawler.arun(url, config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS))
        if not res.success:
            raise RuntimeError(res.error_message or f"status {res.status_code}")
        return str(res.markdown or "")

    return asyncio.run(go())


class CrawlClient:
    def __init__(
        self,
        render: Callable[[str], str] | None = None,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.render = render or _render_with_crawl4ai
        self.http = http or httpx.Client(
            timeout=15, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
        self.sleep, self.clock = sleep, clock
        self._robots: dict[str, RobotFileParser] = {}
        self._last: float | None = None

    def _robots_for(self, url: str) -> RobotFileParser:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            try:
                r = self.http.get(base + "/robots.txt")
                if r.status_code in (401, 403):
                    rp.disallow_all = True
                elif r.status_code >= 400:
                    rp.allow_all = True
                else:
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                rp.disallow_all = True
            self._robots[base] = rp
        return self._robots[base]

    def fetch(self, url: str) -> str:
        url = url.strip()
        if allowed_domain(url) is None:
            raise CrawlRefused("domain not on the allowlist")
        if not self._robots_for(url).can_fetch(USER_AGENT, url):
            raise CrawlRefused("robots.txt disallows this page")
        if self._last is not None:
            wait = MIN_INTERVAL_S - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()
        return self.render(url)
