import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from scout.db import repo
from scout.db.repo import FactIn
from scout.llm.gateway import LLM
from scout.strategy import schemas as S
from scout.strategy.strategist import MAX_FACTS_CHARS, Strategist
from tests.fakes import FakeClient, FakeGuard, FakeMessage, text_block

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 19, 6, 30, tzinfo=UTC)
TODAY = date(2026, 10, 19)


def _assessment(gap_id, **over):
    base = dict(
        gap_id=gap_id,
        scores=S.ComponentScores(proof=20, absence=25, demand=15, founder_fit=12, risk_penalty=3),
        presence_level="absent",
        confidence=0.9,
        hard_filter_failed="none",
        reasoning="strong",
        field_check_question="",
        recommended_status="verified",
    )
    base.update(over)
    return S.GapAssessment(**base)


@pytest.fixture
def seeded(db_session):
    repo.get_or_create_sector(db_session, "pets", "Pets")
    gap, _ = repo.propose_gap(
        db_session, title="Pet sitting marketplace", sector_slug="pets", hypothesis_md="h"
    )
    repo.upsert_fact(
        db_session,
        FactIn(
            claim="Croatia has Pawshake with 10k sitters",
            entity_type="proven_model",
            entity_key="pet-sitting-marketplace",
            confidence=0.8,
            sector_slug="pets",
            source_url="https://x",
        ),
        run_id=1,
        observed_at=NOW - timedelta(minutes=5),
    )
    return gap


def _strategist(db_session, responses):
    return Strategist(LLM(FakeClient(responses), FakeGuard(), Decimal("0.92")), db_session)


def test_schemas_are_structured_output_safe():
    for model in (S.StrategistOutput, S.CriticOutput, S.DirectorReview):
        schema = json.dumps(model.model_json_schema())
        assert '"additionalProperties": false' in schema
        assert all(k not in schema for k in ("minimum", "maximum", "minLength", "pattern"))


def test_collect_inputs_sorted_and_bounded(db_session, seeded):
    st = _strategist(db_session, [])
    inputs = st.collect_inputs(since=NOW - timedelta(hours=1), now=NOW)
    assert inputs.facts[0]["claim"].startswith("Croatia") and inputs.gaps[0]["id"] == seeded.id
    assert inputs.gaps[0]["has_presence_check"] is False
    assert len(json.dumps(inputs.facts)) <= MAX_FACTS_CHARS


def test_assess_and_critique_call_opus_with_cached_system(db_session, seeded):
    out = S.StrategistOutput(assessments=[_assessment(seeded.id)], new_gaps=[], headline="h")
    crit = S.CriticOutput(
        verdicts=[
            S.CriticVerdict(
                gap_id=seeded.id,
                strongest_objection="o",
                kosovo_killer="k",
                risk_penalty=8,
                confidence=0.6,
                decision="needs_field_check",
                field_check_question="Call two vets in Prizren?",
            )
        ]
    )
    client = FakeClient(
        [
            FakeMessage(content=[text_block("{}")], parsed_output=out),
            FakeMessage(content=[text_block("{}")], parsed_output=crit),
        ]
    )
    st = Strategist(LLM(client, FakeGuard(), Decimal("0.92")), db_session)
    inputs = st.collect_inputs(since=NOW - timedelta(hours=1), now=NOW)
    assert st.assess(inputs, TODAY) is out
    assert st.critique(out, inputs, TODAY) is crit
    a, c = client.messages.calls
    assert a["model"] == "claude-opus-5-5" and a["output_config"] == {"effort": "medium"}
    assert c["output_config"] == {"effort": "high"} and c["output_format"] is S.CriticOutput
    assert a["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "2026-10-19" in a["messages"][0]["content"] and "2026" not in "".join(
        b["text"] for b in a["system"]
    )
    assert a["messages"][0]["content"].index('"facts"') > 0


def test_apply_caps_absence_without_presence_check_and_merges_critic(db_session, seeded):
    st = _strategist(db_session, [])
    out = S.StrategistOutput(assessments=[_assessment(seeded.id)], new_gaps=[], headline="h")
    crit = S.CriticOutput(
        verdicts=[
            S.CriticVerdict(
                gap_id=seeded.id,
                strongest_objection="o",
                kosovo_killer="k",
                risk_penalty=8,
                confidence=0.6,
                decision="needs_field_check",
                field_check_question="Call two vets in Prizren?",
            )
        ]
    )
    result = st.apply(out, crit, now=NOW, run_id=7)
    gap = repo.get_gap(db_session, seeded.id)
    assert gap.score_components["absence"] == 12 and gap.score_components["risk"] == 7
    assert gap.score_total == 20 + 12 + 15 + 12 + 7 and gap.confidence == 0.5
    assert gap.status == "verifying" and gap.last_assessed_run_id == 7
    assert (
        result.field_checks_added == 1 and repo.open_field_checks(db_session)[0].gap_id == seeded.id
    )
    assert (
        result.changes[0].old_status == "candidate"
        and result.changes[0].new_score == gap.score_total
    )


def test_apply_verifies_only_with_fresh_check_and_confidence(db_session, seeded):
    repo.upsert_fact(
        db_session,
        FactIn(
            claim="presence check: absent",
            entity_type="presence_check",
            entity_key=f"gap:{seeded.id}",
            confidence=0.8,
            sector_slug="pets",
            value={"verdict": "absent"},
            ttl_days=60,
        ),
        run_id=1,
        observed_at=NOW,
    )
    st = _strategist(db_session, [])
    out = S.StrategistOutput(
        assessments=[_assessment(seeded.id, confidence=0.8)], new_gaps=[], headline="h"
    )
    crit = S.CriticOutput(
        verdicts=[
            S.CriticVerdict(
                gap_id=seeded.id,
                strongest_objection="o",
                kosovo_killer="k",
                risk_penalty=3,
                confidence=0.8,
                decision="proceed",
                field_check_question="",
            )
        ]
    )
    st.apply(out, crit, now=NOW, run_id=8)
    gap = repo.get_gap(db_session, seeded.id)
    assert (
        gap.status == "verified" and gap.score_components["absence"] == 25 and gap.confidence == 0.8
    )


def test_critic_kill_parks_with_flag_and_hard_filter_kills(db_session, seeded):
    repo.get_or_create_sector(db_session, "utilities-household-finance", "Utilities")
    g2, _ = repo.propose_gap(
        db_session, title="Consumer loans app", sector_slug="utilities-household-finance"
    )
    st = _strategist(db_session, [])
    out = S.StrategistOutput(
        assessments=[
            _assessment(seeded.id),
            _assessment(g2.id, hard_filter_failed="regulated-finance-health-gambling"),
        ],
        new_gaps=[],
        headline="h",
    )
    crit = S.CriticOutput(
        verdicts=[
            S.CriticVerdict(
                gap_id=seeded.id,
                strongest_objection="o",
                kosovo_killer="k",
                risk_penalty=15,
                confidence=0.3,
                decision="kill",
                field_check_question="",
            )
        ]
    )
    st.apply(out, crit, now=NOW, run_id=9)
    assert repo.get_gap(db_session, seeded.id).status == "parked"
    assert repo.get_gap(db_session, seeded.id).critic_flag == "critic-says-kill"
    assert (
        repo.get_gap(db_session, g2.id).status == "killed"
        and repo.get_gap(db_session, g2.id).score_total == 0
    )


def test_apply_limits_open_field_checks_and_creates_new_gaps(db_session, seeded):
    for i in range(5):
        repo.add_field_check(db_session, gap_id=seeded.id, question=f"q{i}", why="w", due=TODAY)
    st = _strategist(db_session, [])
    out = S.StrategistOutput(
        assessments=[
            _assessment(
                seeded.id,
                confidence=0.4,
                recommended_status="verifying",
                field_check_question="one more?",
            )
        ],
        new_gaps=[
            S.NewGapIdea(
                title="Dog walking app",
                sector_slug="pets",
                hypothesis="h",
                why_not_yet="w",
                proven_model_slug="",
            ),
            S.NewGapIdea(
                title="Ghost",
                sector_slug="no-such-sector",
                hypothesis="h",
                why_not_yet="w",
                proven_model_slug="",
            ),
        ],
        headline="h",
    )
    result = st.apply(out, S.CriticOutput(verdicts=[]), now=NOW, run_id=10)
    assert result.field_checks_added == 0 and len(repo.open_field_checks(db_session)) == 5
    assert (
        result.new_gaps == 1
        and repo.get_gap_by_title(db_session, "pets", "Dog walking app") is not None
    )


def test_apply_takes_presence_from_the_stored_verdict_not_the_model(db_session, seeded):
    repo.upsert_fact(
        db_session,
        FactIn(
            claim="presence check: exists-but-poor",
            entity_type="presence_check",
            entity_key=f"gap:{seeded.id}",
            confidence=0.8,
            value={"verdict": "exists-but-poor"},
            ttl_days=60,
        ),
        run_id=1,
        observed_at=NOW,
    )
    st = _strategist(db_session, [])
    out = S.StrategistOutput(
        assessments=[_assessment(seeded.id, presence_level="absent")], new_gaps=[], headline="h"
    )
    st.apply(out, S.CriticOutput(verdicts=[]), now=NOW, run_id=8)
    gap = repo.get_gap(db_session, seeded.id)
    assert gap.presence_level == "exists-but-poor" and gap.score_components["absence"] == 18
    inputs = st.collect_inputs(since=NOW - timedelta(hours=1), now=NOW)
    assert inputs.gaps[0]["presence_check_verdict"] == "exists-but-poor"


def test_degraded_presence_check_keeps_the_no_check_caps(db_session, seeded):
    repo.upsert_fact(
        db_session,
        FactIn(
            claim="presence check: unknown",
            entity_type="presence_check",
            entity_key=f"gap:{seeded.id}",
            confidence=0.5,
            value={"verdict": "unknown", "degraded": True, "claimed_verdict": "absent"},
            ttl_days=60,
        ),
        run_id=1,
        observed_at=NOW,
    )
    st = _strategist(db_session, [])
    out = S.StrategistOutput(assessments=[_assessment(seeded.id)], new_gaps=[], headline="h")
    st.apply(out, S.CriticOutput(verdicts=[]), now=NOW, run_id=8)
    gap = repo.get_gap(db_session, seeded.id)
    assert gap.score_components["absence"] == 12 and gap.confidence == 0.5
