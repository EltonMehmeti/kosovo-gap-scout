from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scout.budget.guard import BudgetExceeded, BudgetGuard
from scout.db import repo
from scout.db.repo import CostRecord

pytestmark = pytest.mark.db
DAY = date(2026, 10, 19)


def _rec(eur: str) -> CostRecord:
    return CostRecord("llm", "anthropic", "claude-haiku-5-5", {"input_tokens": 1}, Decimal(eur))


def test_check_raises_when_estimate_exceeds_cap(db_session):
    g = BudgetGuard(db_session, day=DAY, daily_cap_eur=Decimal("1.00"))
    g.check(Decimal("0.90"))
    g.record(_rec("0.70"))
    assert g.remaining() == Decimal("0.300000")
    assert g.can_afford(Decimal("0.30")) and not g.can_afford(Decimal("0.31"))
    with pytest.raises(BudgetExceeded):
        g.check(Decimal("0.31"))


def test_spent_uses_explicit_day(db_session):
    run = repo.start_run(
        db_session,
        day=DAY,
        phase="foundation",
        budget_cap_eur=Decimal("3"),
        started_at=datetime(2026, 10, 18, 23, 30, tzinfo=UTC),
    )
    g_today = BudgetGuard(db_session, day=DAY, daily_cap_eur=Decimal("3"), run_id=run.id)
    g_today.record(_rec("0.50"))
    g_yesterday = BudgetGuard(db_session, day=date(2026, 10, 18), daily_cap_eur=Decimal("3"))
    assert g_today.spent() == Decimal("0.500000")
    assert g_yesterday.spent() == Decimal("0.000000")
    cost_rows = db_session.query(repo.Cost).all()
    assert cost_rows[0].run_id == run.id and cost_rows[0].day == DAY


def test_zero_cap_blocks_everything(db_session):
    g = BudgetGuard(db_session, day=DAY, daily_cap_eur=Decimal("0"))
    with pytest.raises(BudgetExceeded):
        g.check(Decimal("0.000001"))
    g.check(Decimal("0"))  # free calls are always allowed
