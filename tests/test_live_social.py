"""Live checks for the social sources. Run by hand: uv run pytest tests/test_live_social.py -m network -v
Each Apify test spends about $0.01–0.05 of the free credit."""

import os
from datetime import date

import pytest

from scout.sources import social
from scout.sources.apify import ADS_ACTOR, INSTAGRAM_ACTOR, ApifyClient, ad_library_url
from scout.sources.crawl import CrawlClient, crawl_available

pytestmark = pytest.mark.network


@pytest.fixture
def apify():
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        pytest.skip("APIFY_TOKEN not set")
    return ApifyClient(token)


def test_instagram_account_search(apify):
    res = apify.run(
        INSTAGRAM_ACTOR,
        {
            "search": "torta prishtine",
            "searchType": "user",
            "searchLimit": 5,
            "resultsType": "details",
            "resultsLimit": 5,
        },
        max_items=5,
    )
    assert res.items, "no items: check the actor id and input fields"
    assert {"username", "isBusinessAccount", "followersCount"} <= set(res.items[0])
    print(social.instagram_summary(res.items), res.cost_usd)


def test_ad_library_kosovo(apify):
    res = apify.run(
        ADS_ACTOR,
        {"startUrls": [{"url": ad_library_url("")}], "resultsLimit": 5, "isDetailsPerAd": False},
        max_items=5,
    )
    assert res.items, "no items: check the actor id and input fields"
    out = social.ads_summary(res.items, today=date.today())
    assert out["count"] == len(res.items), f"unparsed ad keys: {sorted(res.items[0])}"
    print(out, res.cost_usd)


def test_crawl_merrjep():
    if not crawl_available():
        pytest.skip("crawl extra not installed")
    md = CrawlClient().fetch("https://www.merrjep.com/")
    assert len(md) > 200
