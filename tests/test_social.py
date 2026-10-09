import json
from datetime import date

from scout.sources import social as S
from tests.social_samples import ADS, PROFILES

TODAY = date(2026, 10, 19)


def test_instagram_summary_keeps_only_public_business_accounts():
    out = S.instagram_summary(PROFILES)
    assert out["shops"] == [
        {
            "username": "tortat.e.mira",
            "name": "Tortat e Mira",
            "followers": 5400,
            "category": "Bakery",
            "last_post": "2026-10-01",
            "url": "https://www.instagram.com/tortat.e.mira/",
        }
    ]


def test_instagram_summary_reduces_comments_to_counts():
    out = S.instagram_summary(PROFILES)
    assert out["questions"] == {"price": 1, "delivery": 1, "where": 1}
    dumped = json.dumps(out, ensure_ascii=False)
    for secret in ("private.person", "Sa kushton", "ana.private", "secret.shop"):
        assert secret not in dumped


def test_instagram_summary_caps_shops():
    many = [{"username": f"s{n}", "isBusinessAccount": True} for n in range(40)]
    assert len(S.instagram_summary(many)["shops"]) == 30


def test_normalisers_survive_odd_shapes():
    odd = [
        None,
        "x",
        {"username": None},
        {"username": "a", "isBusinessAccount": True, "latestPosts": "nope"},
        {"adArchiveID": "9", "snapshot": None, "publisherPlatform": "FB"},
    ]
    assert [s["username"] for s in S.instagram_summary(odd)["shops"]] == ["a"]
    assert S.ads_summary(odd, today=TODAY)["count"] == 1
    assert S.instagram_summary(None) == {"shops": [], "questions": S.question_counts([])}


def test_ads_summary_dates_platforms_and_origin():
    out = S.ads_summary(ADS, today=TODAY)
    by_id = {a["ad_archive_id"]: a for a in out["ads"]}
    assert set(by_id) == {"111", "222", "333"}
    local, foreign, unknown = by_id["111"], by_id["222"], by_id["333"]
    assert local["is_foreign"] is False and local["platforms"] == ["facebook", "instagram"]
    assert (local["first_seen"], local["last_seen"]) == ("2025-09-01", "2026-10-19")
    assert local["long_running"] is True and local["page_url"] == "https://facebook.com/tortashop"
    assert foreign["is_foreign"] is True and foreign["long_running"] is False
    assert unknown["is_foreign"] is None and unknown["is_active"] is False
    assert (unknown["first_seen"], unknown["last_seen"]) == ("2025-10-01", "2025-10-06")
    assert (out["count"], out["foreign"], out["long_running"]) == (3, 1, 1)


def test_question_counts_albanian_and_english():
    texts = ["Çmimi?", "how much is it", "a dërgoni në Gjilan", "where can I buy", "nice"]
    assert S.question_counts(texts) == {"price": 2, "delivery": 1, "where": 1}


def test_odd_field_types_do_not_crash_the_normalisers():
    base = {"username": "a", "isBusinessAccount": True}
    shops = S.instagram_summary(
        [base | {"followersCount": "1.2k"}, base | {"username": "b", "followersCount": {"x": 1}}]
    )["shops"]
    assert [s["followers"] for s in shops] == [1200, 0]
    ad = ADS[0] | {"snapshot": {"linkUrl": {"x": 1}, "pageProfileUri": {"y": 2}, "body": "x"}}
    (out,) = S.ads_summary([ad], today=TODAY)["ads"]
    assert out["link_url"] is None and out["page_url"] is None
