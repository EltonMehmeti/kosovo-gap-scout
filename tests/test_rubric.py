# ruff: noqa: E501
import pytest

from scout.strategy import rubric as R


def _score(**over):
    base = dict(
        proof=20,
        absence=25,
        demand=15,
        founder_fit=12,
        risk_penalty=3,
        presence_level="absent",
        has_presence_check=True,
        hard_filter_failed=None,
        confidence=0.8,
    )
    base.update(over)
    return R.score_gap(**base)


def test_full_score_with_presence_check():
    r = _score()
    assert r.total == 20 + 25 + 15 + 12 + (15 - 3) == 84
    assert r.components == {"proof": 20, "absence": 25, "demand": 15, "founder_fit": 12, "risk": 12}
    assert r.confidence == 0.8 and not r.killed


def test_absence_capped_without_presence_check():
    r = _score(has_presence_check=False)
    assert r.components["absence"] == R.NO_CHECK_ABSENCE_CAP == 12
    assert r.confidence == R.NO_CHECK_CONFIDENCE_CAP == 0.5
    assert any("presence check" in reason for reason in r.reasons)


@pytest.mark.parametrize(
    "level,cap",
    [
        ("absent", 25),
        ("exists-but-poor", 18),
        ("prishtina-only", 12),
        ("offline-only", 10),
        ("decent", 0),
        ("unknown", 12),
        ("garbage", 12),
    ],
)
def test_presence_level_caps_absence(level, cap):
    assert _score(presence_level=level).components["absence"] == cap


def test_hard_filter_kills():
    r = _score(hard_filter_failed="cardo-overlap")
    assert r.total == 0 and r.killed and r.reasons == ["hard filter: cardo-overlap"]
    with pytest.raises(ValueError):
        _score(hard_filter_failed="not-a-filter")


def test_components_are_clamped_and_risk_inverted():
    r = _score(proof=99, absence=-5, demand=50, founder_fit=-1, risk_penalty=40)
    assert r.components == {"proof": 25, "absence": 0, "demand": 20, "founder_fit": 0, "risk": 0}
    assert r.total == 45
    assert _score(confidence=1.7).confidence == 1.0


def test_needs_field_check_rule():
    assert (
        R.needs_field_check(60, 0.59)
        and not R.needs_field_check(59, 0.1)
        and not R.needs_field_check(90, 0.6)
    )
    assert R.cap_confidence(0.9, False) == 0.5 and R.cap_confidence(0.9, True) == 0.9
