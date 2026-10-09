import re
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from scout.worker import profiles as P


def test_profiles_match_spec_table():
    assert set(P.PROFILES) == {
        "map-sector",
        "hunt-models",
        "verify-gap",
        "culture",
        "news-scan",
        "deep-dive",
    }
    ms = P.PROFILES["map-sector"]
    assert (ms.model, ms.max_searches, ms.max_fetches, ms.max_iterations, ms.est_cost_eur) == (
        "claude-sonnet-5-5",
        12,
        8,
        14,
        Decimal("0.35"),
    )
    vg = P.PROFILES["verify-gap"]
    assert (vg.max_searches, vg.max_fetches, vg.est_cost_eur) == (10, 6, Decimal("0.40"))
    ns = P.PROFILES["news-scan"]
    assert (ns.max_searches, ns.max_fetches, ns.max_iterations, ns.est_cost_eur) == (
        4,
        4,
        6,
        Decimal("0.10"),
    )
    dd = P.PROFILES["deep-dive"]
    assert (dd.model, dd.effort, dd.est_cost_eur) == ("claude-opus-5-5", "high", Decimal("0.80"))
    for p in P.PROFILES.values():
        assert "{contract}" in p.brief_template or p.name == "deep-dive"


def test_build_brief_fills_payload_and_context():
    brief = P.build_brief(
        P.PROFILES["map-sector"],
        {"sector": "pets", "sector_name": "Pets"},
        date(2026, 10, 19),
        journal_md="- yesterday: mapped cars",
        sector_digest="old digest",
    )
    assert "2026-10-19" in brief and "`pets`" in brief and "Pets" in brief
    assert "old digest" in brief and "mapped cars" in brief
    assert "leads:" in brief and "150 words" in brief
    assert "{" not in brief.replace('{"', "")  # no unfilled placeholders (JSON examples allowed)


def test_build_brief_missing_keys_become_none_marker():
    brief = P.build_brief(
        P.PROFILES["verify-gap"], {"gap_id": 7, "gap_title": "Pet sitting"}, date(2026, 10, 19)
    )
    assert "gap:7" in brief and "Pet sitting" in brief and "(none)" in brief


def test_build_system_is_frozen_and_cached():
    class FakeSession:
        pass

    digests = {"country": "Kosovo has 1.6M people."}
    culture = [
        SimpleNamespace(
            key="culture:payments-and-trust", title="Payments and trust", body_md="Cash dominates."
        )
    ]
    system = P.build_system(
        FakeSession(),
        get_digest=lambda s, k: digests.get(k),
        list_digests=lambda s, prefix: culture,
    )
    assert [b["type"] for b in system] == ["text", "text"]
    assert system[-1]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in system[0]
    assert "Kosovo has 1.6M people." in system[1]["text"] and "Cash dominates." in system[1]["text"]
    joined = system[0]["text"] + system[1]["text"]
    assert not re.search(r"\b20\d\d-\d\d-\d\d\b", joined)
    assert system == P.build_system(
        FakeSession(),
        get_digest=lambda s, k: digests.get(k),
        list_digests=lambda s, prefix: culture,
    )


def test_journal_markdown_limits_size():
    entries = [
        SimpleNamespace(
            day=date(2026, 10, 18), did_md="a" * 5000, learned_md="b" * 5000, tomorrow_md="c"
        )
    ]
    md = P.journal_markdown(entries, limit_chars=1000)
    assert len(md) <= 1000 and md.startswith("### 2026-10-18")


def test_unknown_profile_payload_type_rejected():
    with pytest.raises(TypeError):
        P.build_brief(P.PROFILES["culture"], ["not", "a", "dict"], date(2026, 10, 19))
