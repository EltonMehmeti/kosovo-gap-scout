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


def _presence(db_session, gap, *, verdict="absent", observed_at=NOW, key=None):
    repo.upsert_fact(
        db_session,
        FactIn(
            claim=f"presence check: {verdict} ({observed_at.date()})",
            entity_type="presence_check",
            entity_key=key or f"gap:{gap.id}",
            confidence=0.8,
            sector_slug="pets",
            value={"verdict": verdict},
            ttl_days=60,
        ),
        run_id=1,
        observed_at=observed_at,
    )


def _payment_path(db_session, gap_id):
    repo.upsert_fact(
        db_session,
        FactIn(
            claim="Customers can pay by card through a local PSP",
            entity_type="payment_path",
            entity_key=f"gap:{gap_id}",
            confidence=0.7,
            sector_slug="pets",
        ),
        run_id=1,
        observed_at=NOW,
    )


def _proven_model(db_session, gap, markets):
    pm = repo.upsert_proven_model(
        db_session,
        slug="pet-sitting",
        name="Pet sitting",
        sector_slug="pets",
        description="d",
        markets=markets,
    )
    gap.proven_model_id = pm.id
    db_session.commit()


CITED = [
    {"country": "HR", "example": "Pawshake", "url": "https://pawshake.hr"},
    {"country": "DE", "example": "Rover", "url": "https://rover.de"},
]


def _ready(db_session, gap):
    """Everything spec A10 asks for, so each test can remove exactly one condition."""
    _presence(db_session, gap)
    _proven_model(db_session, gap, CITED)
    _payment_path(db_session, gap.id)


def _verdict(gap_id, decision="proceed", **over):
    base = dict(
        gap_id=gap_id,
        strongest_objection="o",
        kosovo_killer="k",
        risk_penalty=3,
        confidence=0.8,
        decision=decision,
        field_check_question="Ask a vet?" if decision == "needs_field_check" else "",
    )
    base.update(over)
    return S.CriticVerdict(**base)


def _apply(db_session, gap, *, verdicts, run_id=8, **assessment):
    st = _strategist(db_session, [])
    a = _assessment(gap.id, **({"confidence": 0.8} | assessment))
    out = S.StrategistOutput(assessments=[a], new_gaps=[], headline="h")
    return st.apply(out, S.CriticOutput(verdicts=verdicts), now=NOW, run_id=run_id)


def test_apply_verifies_when_every_a10_condition_holds(db_session, seeded):
    _ready(db_session, seeded)
    result = _apply(db_session, seeded, verdicts=[_verdict(seeded.id)])
    gap = repo.get_gap(db_session, seeded.id)
    assert (
        gap.status == "verified" and gap.score_components["absence"] == 25 and gap.confidence == 0.8
    )
    assert result.field_checks_added == 0


def _no_check(db_session, gap):
    from scout.db.models import Fact

    db_session.query(Fact).filter(Fact.entity_type == "presence_check").delete()
    db_session.commit()


def _old_check(db_session, gap):
    _no_check(db_session, gap)
    _presence(db_session, gap, observed_at=NOW - timedelta(days=31))


def _unknown_check(db_session, gap):
    _no_check(db_session, gap)
    _presence(db_session, gap, verdict="unknown")


def _one_citation(db_session, gap):
    from scout.db.models import ProvenModel

    db_session.get(ProvenModel, gap.proven_model_id).markets = CITED[:1]
    db_session.commit()


def _uncited_markets(db_session, gap):
    from scout.db.models import ProvenModel

    db_session.get(ProvenModel, gap.proven_model_id).markets = [
        {"country": "HR", "example": "Pawshake"},
        {"country": "DE", "example": "Rover"},
    ]
    db_session.commit()


def _no_nearby(db_session, gap):
    from scout.db.models import ProvenModel

    db_session.get(ProvenModel, gap.proven_model_id).markets = [
        {"country": "DE", "example": "Rover", "url": "https://rover.de"},
        {"country": "US", "example": "Wag", "url": "https://wag.com"},
    ]
    db_session.commit()


def _no_model(db_session, gap):
    gap.proven_model_id = None
    db_session.commit()


def _no_payment(db_session, gap):
    from scout.db.models import Fact

    db_session.query(Fact).filter(Fact.entity_type == "payment_path").delete()
    db_session.commit()


def _payment_for_other_gap(db_session, gap):
    _no_payment(db_session, gap)
    _payment_path(db_session, gap.id + 100)


def _open_field_check(db_session, gap):
    repo.add_field_check(db_session, gap_id=gap.id, question="q", why="w", due=TODAY)


@pytest.mark.parametrize(
    "breaker",
    [
        _no_check,
        _old_check,
        _unknown_check,
        _one_citation,
        _uncited_markets,
        _no_nearby,
        _no_model,
        _no_payment,
        _payment_for_other_gap,
        _open_field_check,
    ],
)
def test_each_missing_a10_condition_blocks_verified(db_session, seeded, breaker):
    _ready(db_session, seeded)
    breaker(db_session, seeded)
    _apply(db_session, seeded, verdicts=[_verdict(seeded.id)])
    assert repo.get_gap(db_session, seeded.id).status != "verified"


def test_no_critic_verdict_blocks_verified(db_session, seeded):
    _ready(db_session, seeded)
    _apply(db_session, seeded, verdicts=[])
    assert repo.get_gap(db_session, seeded.id).status == "verifying"


def test_low_confidence_blocks_verified(db_session, seeded):
    _ready(db_session, seeded)
    _apply(db_session, seeded, verdicts=[_verdict(seeded.id)], confidence=0.65)
    assert repo.get_gap(db_session, seeded.id).status == "verifying"


def test_score_below_verifying_floor_blocks_verified(db_session, seeded):
    _ready(db_session, seeded)
    weak = S.ComponentScores(proof=5, absence=10, demand=5, founder_fit=5, risk_penalty=10)
    _apply(db_session, seeded, verdicts=[_verdict(seeded.id)], scores=weak)
    assert repo.get_gap(db_session, seeded.id).status == "candidate"


def test_needs_field_check_counts_once_the_founder_answered(db_session, seeded):
    _ready(db_session, seeded)
    fc = repo.add_field_check(db_session, gap_id=seeded.id, question="q", why="w", due=TODAY)
    _apply(db_session, seeded, verdicts=[_verdict(seeded.id, "needs_field_check")])
    assert repo.get_gap(db_session, seeded.id).status != "verified"  # still open
    open_now = repo.open_field_checks(db_session)
    assert fc.id in {c.id for c in open_now} and len(open_now) == 2  # + the critic's question
    for c in open_now:
        repo.answer_field_check(db_session, c, answer="yes, 3 vets", answered_at=NOW)
    result = _apply(db_session, seeded, verdicts=[_verdict(seeded.id, "needs_field_check")])
    assert repo.get_gap(db_session, seeded.id).status == "verified"
    assert result.field_checks_added == 0 and repo.open_field_checks(db_session) == []


def test_needs_field_check_with_nothing_answered_blocks_verified(db_session, seeded):
    _ready(db_session, seeded)
    _apply(db_session, seeded, verdicts=[_verdict(seeded.id, "needs_field_check")])
    assert repo.get_gap(db_session, seeded.id).status == "verifying"


# ---------- Minor 3: verified does not flap ----------


def _make_verified(db_session, gap):
    _ready(db_session, gap)
    _apply(db_session, gap, verdicts=[_verdict(gap.id)], run_id=8)
    assert repo.get_gap(db_session, gap.id).status == "verified"


def test_verified_stays_verified_without_new_evidence(db_session, seeded):
    _make_verified(db_session, seeded)
    _apply(db_session, seeded, verdicts=[], run_id=9, recommended_status="verifying")
    assert repo.get_gap(db_session, seeded.id).status == "verified"


@pytest.mark.parametrize("decision", ["park", "kill"])
def test_verified_demoted_by_critic_park_or_kill(db_session, seeded, decision):
    _make_verified(db_session, seeded)
    _apply(db_session, seeded, verdicts=[_verdict(seeded.id, decision)], run_id=9)
    assert repo.get_gap(db_session, seeded.id).status == "parked"


def test_verified_demoted_when_check_expires(db_session, seeded):
    _make_verified(db_session, seeded)
    st = _strategist(db_session, [])
    out = S.StrategistOutput(assessments=[_assessment(seeded.id)], new_gaps=[], headline="h")
    st.apply(out, S.CriticOutput(verdicts=[]), now=NOW + timedelta(days=31), run_id=9)
    assert repo.get_gap(db_session, seeded.id).status == "verifying"


def test_verified_demoted_when_confidence_drops(db_session, seeded):
    _make_verified(db_session, seeded)
    _apply(db_session, seeded, verdicts=[], run_id=9, confidence=0.6)
    assert repo.get_gap(db_session, seeded.id).status == "verifying"


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


# ---------- Minor 6: the Critic sees the top three by the rubric-capped total ----------


def test_critique_ranks_by_rubric_capped_total(db_session, seeded):
    g2, _ = repo.propose_gap(db_session, title="Dog walking app", sector_slug="pets")
    _presence(db_session, g2)  # g2 has a check: its absence of 20 counts in full
    # raw sums: seeded 70 > g2 65; rubric totals: seeded 25+12(no check)+10+10+15 = 72 < g2 80
    a1 = _assessment(
        seeded.id,
        scores=S.ComponentScores(proof=25, absence=25, demand=10, founder_fit=10, risk_penalty=0),
    )
    a2 = _assessment(
        g2.id,
        scores=S.ComponentScores(proof=25, absence=20, demand=10, founder_fit=10, risk_penalty=0),
    )
    out = S.StrategistOutput(assessments=[a1, a2], new_gaps=[], headline="h")
    client = FakeClient(
        [FakeMessage(content=[text_block("{}")], parsed_output=S.CriticOutput(verdicts=[]))]
    )
    st = Strategist(LLM(client, FakeGuard(), Decimal("0.92")), db_session)
    inputs = st.collect_inputs(since=NOW - timedelta(hours=1), now=NOW)
    st.critique(out, inputs, TODAY, top_n=1)
    sent = json.loads(client.messages.calls[0]["messages"][0]["content"])
    assert [a["gap_id"] for a in sent["assessments"]] == [g2.id]


# ---------- C2: bounded Strategist input, sized output, Critic failure ----------


class RecordingGuard(FakeGuard):
    def __init__(self):
        super().__init__()
        self.checks = []

    def check(self, est_eur):
        self.checks.append(Decimal(est_eur))
        super().check(est_eur)


def _fact(db_session, claim, *, sector=None, key="k", observed_at=NOW, etype="stat"):
    return repo.upsert_fact(
        db_session,
        FactIn(claim=claim, entity_type=etype, entity_key=key, confidence=0.7, sector_slug=sector),
        run_id=1,
        observed_at=observed_at,
    )


def test_changes_today_unions_fact_sectors_gap_keyed_facts_and_touched_gaps(db_session, seeded):
    from scout.strategy.strategist import changes_today

    for slug in ("home-services", "weddings", "tutoring"):
        repo.get_or_create_sector(db_session, slug, slug)
    g_home, _ = repo.propose_gap(db_session, title="Cleaners", sector_slug="home-services")
    g_wed, _ = repo.propose_gap(db_session, title="Venues", sector_slug="weddings")
    repo.propose_gap(db_session, title="Tutors", sector_slug="tutoring")  # untouched
    facts = [
        _fact(db_session, "pets fact", sector="pets"),
        _fact(db_session, "about cleaners", key=f"gap:{g_home.id}", etype="gap"),
        _fact(db_session, "country stat"),
    ]
    sectors, gap_ids = changes_today(db_session, facts, {g_wed.id})
    assert sectors == ["home-services", "pets", "weddings"]
    assert gap_ids == {g_home.id, g_wed.id}
    assert changes_today(db_session, [_fact(db_session, "country only")], set()) == ([], set())


def test_collect_inputs_scopes_to_changed_sectors(db_session, seeded):
    repo.get_or_create_sector(db_session, "weddings", "Weddings")
    other, _ = repo.propose_gap(db_session, title="Venues", sector_slug="weddings")
    _fact(db_session, "wedding fact", sector="weddings")
    _fact(db_session, "about pet gap", key=f"gap:{seeded.id}", etype="presence_check")
    st = _strategist(db_session, [])
    inputs = st.collect_inputs(since=NOW - timedelta(hours=1), now=NOW, sector_slugs=["pets"])
    assert [g["id"] for g in inputs.gaps] == [seeded.id]
    claims = {f["claim"] for f in inputs.facts}
    assert "about pet gap" in claims and "wedding fact" not in claims
    assert set(inputs.sector_digests) == {"pets"} and other.id not in {g["id"] for g in inputs.gaps}


def test_collect_inputs_caps_gaps_touched_then_unscored_then_stalest(db_session, seeded):
    from scout.db.models import Gap
    from scout.strategy.strategist import MAX_STRATEGY_GAPS

    ids = [seeded.id]
    for i in range(24):
        g, _ = repo.propose_gap(db_session, title=f"Gap {i}", sector_slug="pets")
        ids.append(g.id)
    # 20 scored, assessed in runs 100..119 (ids[5:] ; ids[5] is stalest); ids[0:5] unscored
    for n, gid in enumerate(ids[5:]):
        g = db_session.get(Gap, gid)
        g.score_components, g.score_total, g.last_assessed_run_id = {"proof": 1}, 1, 100 + n
    for gid in ids[:5]:
        db_session.get(Gap, gid).last_assessed_run_id = None
    db_session.commit()
    touched = {ids[-1]}  # most recently assessed, but touched today
    st = _strategist(db_session, [])
    inputs = st.collect_inputs(
        since=NOW - timedelta(hours=1), now=NOW, sector_slugs=["pets"], priority_gap_ids=touched
    )
    chosen = {g["id"] for g in inputs.gaps}
    assert len(chosen) == MAX_STRATEGY_GAPS == 15
    assert ids[-1] in chosen and set(ids[:5]) <= chosen
    assert set(ids[5:14]) <= chosen and not (set(ids[14:-1]) & chosen)  # 9 stalest scored
    assert [g["id"] for g in inputs.gaps] == sorted(chosen)


def test_collect_inputs_total_size_is_bounded(db_session, seeded):
    from scout.strategy.strategist import MAX_INPUT_CHARS

    for i in range(400):
        _fact(db_session, f"{i} " + "x" * 900, sector="pets", key=f"k{i}")
    for i in range(30):
        repo.get_or_create_sector(db_session, f"s{i}", f"S{i}")
        repo.set_digest(db_session, f"sector:s{i}", "t", "d" * 5000, now=NOW)
        repo.propose_gap(db_session, title=f"G{i}", sector_slug=f"s{i}", hypothesis_md="h" * 2000)
    st = _strategist(db_session, [])
    slugs = ["pets", *(f"s{i}" for i in range(30))]
    inputs = st.collect_inputs(since=NOW - timedelta(hours=1), now=NOW, sector_slugs=slugs)
    assert len(st.payload(inputs, TODAY)) <= MAX_INPUT_CHARS
    assert len(inputs.gaps) == 15 and len(inputs.sector_digests) <= 8 and inputs.facts


@pytest.mark.parametrize("n_gaps", [1, 15])
def test_assess_sizes_max_tokens_and_estimate_from_the_gap_count(db_session, seeded, n_gaps):
    from scout.strategy.strategist import strategist_max_tokens

    for i in range(n_gaps - 1):
        repo.propose_gap(db_session, title=f"Gap {i}", sector_slug="pets")
    out = S.StrategistOutput(assessments=[], new_gaps=[], headline="h")
    client = FakeClient([FakeMessage(content=[text_block("{}")], parsed_output=out)])
    guard = RecordingGuard()
    st = Strategist(LLM(client, guard, Decimal("0.92")), db_session)
    inputs = st.collect_inputs(since=NOW - timedelta(hours=1), now=NOW, sector_slugs=["pets"])
    st.assess(inputs, TODAY)
    call = client.messages.calls[0]
    assert call["max_tokens"] == strategist_max_tokens(n_gaps) <= 16_000
    assert strategist_max_tokens(15) >= 15 * 600  # room for thinking + ~200 tokens per assessment
    # the estimate covers a full-length answer at Opus output prices
    assert guard.checks[0] >= Decimal(call["max_tokens"]) * Decimal("20") / 1_000_000 * Decimal(
        "0.92"
    )


def test_critique_has_room_to_answer(db_session, seeded):
    out = S.StrategistOutput(assessments=[_assessment(seeded.id)], new_gaps=[], headline="h")
    client = FakeClient(
        [FakeMessage(content=[text_block("{}")], parsed_output=S.CriticOutput(verdicts=[]))]
    )
    st = Strategist(LLM(client, FakeGuard(), Decimal("0.92")), db_session)
    st.critique(out, st.collect_inputs(since=NOW - timedelta(hours=1), now=NOW), TODAY)
    assert client.messages.calls[0]["max_tokens"] >= 8192


def test_without_critic_scores_cannot_rise_and_first_scores_apply(db_session, seeded):
    from scout.db.models import Gap

    fresh, _ = repo.propose_gap(db_session, title="Dog walking", sector_slug="pets")
    g = db_session.get(Gap, seeded.id)
    g.score_total, g.confidence, g.status = 40, 0.4, "candidate"
    g.score_components = {"proof": 10, "absence": 10, "demand": 5, "founder_fit": 5, "risk": 10}
    db_session.commit()
    st = _strategist(db_session, [])
    out = S.StrategistOutput(
        assessments=[_assessment(seeded.id), _assessment(fresh.id)], new_gaps=[], headline="h"
    )
    st.apply(out, S.CriticOutput(verdicts=[]), now=NOW, run_id=11, critic_ok=False)
    g = repo.get_gap(db_session, seeded.id)
    assert g.score_total == 40 and g.confidence == 0.4 and g.status == "candidate"
    assert g.score_components["proof"] == 10
    f = repo.get_gap(db_session, fresh.id)
    assert f.score_total == 20 + 12 + 15 + 12 + 12 and f.status == "verifying"


def test_without_critic_scores_may_fall(db_session, seeded):
    from scout.db.models import Gap

    g = db_session.get(Gap, seeded.id)
    g.score_total, g.confidence = 90, 0.9
    g.score_components = {"proof": 25, "absence": 25, "demand": 20, "founder_fit": 10, "risk": 10}
    db_session.commit()
    st = _strategist(db_session, [])
    out = S.StrategistOutput(assessments=[_assessment(seeded.id)], new_gaps=[], headline="h")
    st.apply(out, S.CriticOutput(verdicts=[]), now=NOW, run_id=11, critic_ok=False)
    g = repo.get_gap(db_session, seeded.id)
    assert g.score_total == 20 + 12 + 15 + 12 + 12 and g.confidence == 0.5


def test_founder_parked_gap_is_not_reassessed_and_keeps_its_status(db_session, seeded):
    from scout import founder

    scout_parked, _ = repo.propose_gap(db_session, title="Scout parked", sector_slug="pets")
    scout_parked.status = "parked"
    db_session.commit()
    founder.set_gap_status(db_session, seeded.id, "park", today=TODAY, now=NOW)
    st = _strategist(db_session, [])
    inputs = st.collect_inputs(since=NOW - timedelta(hours=1), now=NOW)
    ids = {g["id"] for g in inputs.gaps}
    assert seeded.id not in ids and scout_parked.id in ids
    # even if the model assesses it anyway, apply leaves it parked
    out = S.StrategistOutput(
        assessments=[_assessment(seeded.id, recommended_status="verified")],
        new_gaps=[],
        headline="h",
    )
    st.apply(out, S.CriticOutput(verdicts=[]), now=NOW, run_id=8)
    assert repo.get_gap(db_session, seeded.id).status == "parked"
    # a scout-parked gap is still revivable
    out = S.StrategistOutput(
        assessments=[_assessment(scout_parked.id, recommended_status="candidate")],
        new_gaps=[],
        headline="h",
    )
    st.apply(out, S.CriticOutput(verdicts=[]), now=NOW, run_id=8)
    assert repo.get_gap(db_session, scout_parked.id).status != "parked"
