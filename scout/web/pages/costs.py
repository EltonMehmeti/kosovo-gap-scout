"""Budget & costs: today's limit and where it comes from, 14 days of spend, cost per model, and
source health; the founder can set or clear today's cap."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import Cost, Source
from scout.director.planner import PHASE_RULES
from scout.founder import FounderError
from scout.web import ui
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()
CHART_DAYS = 14


@router.get("/costs", response_class=HTMLResponse)
def costs_page(request: Request, session: Session = Depends(get_session)):
    settings = request.app.state.settings
    day = local_day(request)
    month_start = day.replace(day=1)
    total = func.sum(Cost.cost_eur)
    by_day = dict(
        session.execute(
            select(Cost.day, total)
            .where(Cost.day >= day - timedelta(days=CHART_DAYS - 1), Cost.day <= day)
            .group_by(Cost.day)
        ).all()
    )
    bars = [
        (d, by_day.get(d) or Decimal("0"))
        for d in (day - timedelta(days=n) for n in range(CHART_DAYS - 1, -1, -1))
    ]
    per_model = session.execute(
        select(Cost.kind, Cost.provider, Cost.model, func.count(), total)
        .where(Cost.day >= month_start, Cost.day <= day)
        .group_by(Cost.kind, Cost.provider, Cost.model)
        .order_by(total.desc())
    ).all()
    phase = (repo.get_setting(session, "phase") or {}).get("value") or settings.phase
    founder_cap = founder.today_cap(session, day)
    if founder_cap is not None:
        cap_source = "your cap for today"
    elif PHASE_RULES[phase]["cap"] <= Decimal(settings.daily_budget_eur):
        cap_source = f"the {ui.phase_info(phase).text} phase cap"
    else:
        cap_source = "the daily budget (SCOUT_DAILY_BUDGET_EUR on Render)"
    return page(
        request,
        "costs.html",
        day=day,
        apify_used=repo.apify_usd_in_month(session, day),
        apify_cap=Decimal(settings.apify_monthly_usd),
        spent_today=repo.spent_on(session, day),
        spent_month=repo.spent_between(session, month_start, day),
        cap=founder.effective_cap(session, settings, phase, day),
        cap_source=cap_source,
        founder_cap=founder_cap,
        max_cap=founder.MAX_TODAY_CAP_EUR,
        bars=bars,
        bar_max=max(eur for _, eur in bars),
        per_model=per_model,
        sources=session.scalars(select(Source).order_by(Source.tier, Source.name)).all(),
    )


@router.post("/costs/cap")
def set_cap(request: Request, eur: str = Form(""), session: Session = Depends(get_session)):
    try:
        value = founder.set_today_cap(session, eur, today=local_day(request))
    except FounderError as e:
        return back("/costs", err=str(e))
    return back(
        "/costs", msg=f"Today's cap: €{value}" if value is not None else "Today's cap cleared"
    )
