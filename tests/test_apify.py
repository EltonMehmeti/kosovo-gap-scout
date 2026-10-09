from decimal import Decimal

import httpx
import pytest

from scout.sources.apify import INSTAGRAM_ACTOR, ApifyClient, ApifyError, ad_library_url

RUN = "/v2/acts/apify~instagram-scraper/runs"
RUN_GET = "/v2/actor-runs/r1"


def _run(status, cost=0.031):
    return {"data": {"id": "r1", "status": status, "defaultDatasetId": "d1", "usageTotalUsd": cost}}


def _client(routes):
    calls = []

    def handler(request):
        calls.append(request)
        resp = routes.get((request.method, request.url.path))
        if resp is None:
            return httpx.Response(404, json={"error": {"message": "not found"}})
        return resp

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return ApifyClient("tok", http=http), calls


def test_run_returns_items_and_real_cost():
    client, calls = _client(
        {
            ("POST", RUN): httpx.Response(201, json=_run("SUCCEEDED")),
            ("GET", "/v2/datasets/d1/items"): httpx.Response(200, json=[{"username": "a"}]),
        }
    )
    res = client.run(INSTAGRAM_ACTOR, {"search": "torta"}, max_items=30)
    assert res.items == [{"username": "a"}] and res.cost_usd == Decimal("0.031")
    params = calls[0].url.params
    assert (params["maxItems"], params["timeout"], params["waitForFinish"]) == ("30", "120", "60")
    assert calls[0].headers["Authorization"] == "Bearer tok"
    assert calls[1].url.params["limit"] == "30"


def test_run_keeps_at_most_max_items():
    client, _ = _client(
        {
            ("POST", RUN): httpx.Response(201, json=_run("SUCCEEDED")),
            ("GET", "/v2/datasets/d1/items"): httpx.Response(
                200, json=[{"i": n} for n in range(9)]
            ),
        }
    )
    assert len(client.run(INSTAGRAM_ACTOR, {}, max_items=5).items) == 5


def test_run_polls_until_finished():
    client, _ = _client(
        {
            ("POST", RUN): httpx.Response(201, json=_run("RUNNING")),
            ("GET", RUN_GET): httpx.Response(200, json=_run("SUCCEEDED", 0.04)),
            ("GET", "/v2/datasets/d1/items"): httpx.Response(200, json=[]),
        }
    )
    assert client.run(INSTAGRAM_ACTOR, {}, max_items=30).cost_usd == Decimal("0.04")


def test_timeout_aborts_and_keeps_the_cost():
    client, calls = _client(
        {
            ("POST", RUN): httpx.Response(201, json=_run("RUNNING")),
            ("GET", RUN_GET): httpx.Response(200, json=_run("RUNNING", 0.02)),
            ("POST", "/v2/actor-runs/r1/abort"): httpx.Response(200, json=_run("ABORTING")),
        }
    )
    with pytest.raises(ApifyError, match="timed out") as e:
        client.run(INSTAGRAM_ACTOR, {}, max_items=30)
    assert e.value.cost_usd == Decimal("0.02")
    assert any(c.url.path.endswith("/abort") for c in calls)


def test_failed_run_raises_with_its_cost():
    client, _ = _client({("POST", RUN): httpx.Response(201, json=_run("FAILED", 0.01))})
    with pytest.raises(ApifyError, match="run failed") as e:
        client.run(INSTAGRAM_ACTOR, {}, max_items=30)
    assert e.value.cost_usd == Decimal("0.01")


def test_http_error_carries_the_api_message():
    body = {"error": {"message": "Monthly usage hard limit exceeded"}}
    client, _ = _client({("POST", RUN): httpx.Response(402, json=body)})
    with pytest.raises(ApifyError, match="hard limit") as e:
        client.run(INSTAGRAM_ACTOR, {}, max_items=30)
    assert e.value.cost_usd == Decimal("0")


def test_ad_library_url():
    assert "country=XK" in ad_library_url("") and "q=" not in ad_library_url("")
    url = ad_library_url("torta ditelindje")
    assert "q=torta+ditelindje" in url and "search_type=keyword_unordered" in url


def test_failure_after_the_run_started_keeps_the_run_cost():
    client, _ = _client({("POST", RUN): httpx.Response(201, json=_run("SUCCEEDED"))})
    with pytest.raises(ApifyError) as e:
        client.run(INSTAGRAM_ACTOR, {}, max_items=30)
    assert e.value.cost_usd == Decimal("0.031")
    client, _ = _client({("POST", RUN): httpx.Response(201, json=_run("RUNNING"))})
    with pytest.raises(ApifyError) as e:
        client.run(INSTAGRAM_ACTOR, {}, max_items=30)
    assert e.value.cost_usd == Decimal("0.031")
