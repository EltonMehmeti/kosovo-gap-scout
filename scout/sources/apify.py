"""Apify REST client: start an actor run, wait up to a timeout, return its dataset items and real cost."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlencode

import httpx

API = "https://api.apify.com/v2"
INSTAGRAM_ACTOR = "apify~instagram-scraper"
ADS_ACTOR = "apify~facebook-ads-scraper"
WAIT_STEP_S = 60  # the API holds a waitForFinish request for at most 60 s
FINISHED = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


class ApifyError(RuntimeError):
    def __init__(self, message: str, cost_usd: Decimal = Decimal("0")) -> None:
        super().__init__(message)
        self.cost_usd = cost_usd


@dataclass
class ActorResult:
    items: list[dict]
    cost_usd: Decimal
    run_id: str


def ad_library_url(query: str, country: str = "XK") -> str:
    params = {"active_status": "active", "ad_type": "all", "country": country, "media_type": "all"}
    if query.strip():
        params |= {"q": query.strip(), "search_type": "keyword_unordered"}
    return "https://www.facebook.com/ads/library/?" + urlencode(params)


def _cost(run: dict) -> Decimal:
    return Decimal(str(run.get("usageTotalUsd") or 0))


def _error_text(r: httpx.Response) -> str:
    try:
        return str(r.json()["error"]["message"])[:200]
    except (ValueError, KeyError, TypeError):
        return r.text[:200]


class ApifyClient:
    def __init__(self, token: str, http: httpx.Client | None = None, timeout_s: int = 120) -> None:
        self.http = http or httpx.Client(timeout=WAIT_STEP_S + 15)
        self.headers = {"Authorization": f"Bearer {token}"}
        self.timeout_s = timeout_s

    def _request(self, method: str, path: str, **kwargs):
        r = self.http.request(method, f"{API}{path}", headers=self.headers, **kwargs)
        if r.status_code >= 400:
            raise ApifyError(f"apify {r.status_code}: {_error_text(r)}")
        return r.json()

    def run(self, actor: str, actor_input: dict, *, max_items: int) -> ActorResult:
        params = {"timeout": self.timeout_s, "maxItems": max_items, "waitForFinish": WAIT_STEP_S}
        run = self._request("POST", f"/acts/{actor}/runs", params=params, json=actor_input)["data"]
        try:
            return self._finish(run, max_items)
        except ApifyError as e:
            raise ApifyError(str(e), e.cost_usd or _cost(run)) from e
        except httpx.HTTPError as e:
            raise ApifyError(type(e).__name__, _cost(run)) from e

    def _finish(self, run: dict, max_items: int) -> ActorResult:
        waited = WAIT_STEP_S
        while run["status"] not in FINISHED and waited < self.timeout_s:
            run = self._request(
                "GET", f"/actor-runs/{run['id']}", params={"waitForFinish": WAIT_STEP_S}
            )["data"]
            waited += WAIT_STEP_S
        if run["status"] not in FINISHED:
            self._request("POST", f"/actor-runs/{run['id']}/abort")
            run = self._request("GET", f"/actor-runs/{run['id']}")["data"]
            raise ApifyError(f"timed out after {self.timeout_s} s", _cost(run))
        if run["status"] != "SUCCEEDED":
            raise ApifyError(f"run {run['status'].lower()}", _cost(run))
        try:
            items = self._request(
                "GET",
                f"/datasets/{run['defaultDatasetId']}/items",
                params={"clean": "true", "limit": max_items},
            )
        except (ApifyError, httpx.HTTPError) as e:
            raise ApifyError(str(e) or type(e).__name__, _cost(run)) from e
        return ActorResult(items=list(items)[:max_items], cost_usd=_cost(run), run_id=run["id"])
