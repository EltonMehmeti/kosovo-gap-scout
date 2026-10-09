from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from scout.db import repo
from scout.db.repo import CostRecord


class BudgetExceeded(RuntimeError):
    pass


class BudgetGuard:
    """Hard stop before every paid call; ledger entry after it.

    `day` is the run's local (Kosovo) date, decided once by the Director — never
    derived from the wall clock at record time.
    """

    def __init__(
        self,
        session: Session,
        *,
        day: date,
        daily_cap_eur: Decimal,
        run_id: int | None = None,
    ) -> None:
        self.session = session
        self.day = day
        self.cap = Decimal(daily_cap_eur)
        self.run_id = run_id

    def spent(self) -> Decimal:
        return repo.spent_on(self.session, self.day)

    def remaining(self) -> Decimal:
        return max(Decimal("0"), self.cap - self.spent()).quantize(Decimal("0.000001"))

    def can_afford(self, est_eur: Decimal) -> bool:
        return self.spent() + Decimal(est_eur) <= self.cap

    def check(self, est_eur: Decimal) -> None:
        spent = self.spent()
        if spent + Decimal(est_eur) > self.cap:
            raise BudgetExceeded(
                f"budget: spent {spent} + est {est_eur} > cap {self.cap} for {self.day}"
            )

    def record(self, rec: CostRecord) -> Decimal:
        repo.record_cost(self.session, rec, day=self.day, run_id=self.run_id)
        return self.spent()
