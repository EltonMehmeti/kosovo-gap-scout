"""Costs: spend per day and per model, today's cap, source health; the founder can set today's cap."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import Cost, Source
from scout.founder import FounderError
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/costs", response_class=HTMLResponse)
def costs_page(request: Request, session: Session = Depends(get_session)):
    settings = request.app.state.settings
    day = local_day(request)
    month_start = day.replace(day=1)
    total = func.sum(Cost.cost_eur)
    per_day = session.execute(
        select(Cost.day, total)
        .where(Cost.day >= day - timedelta(days=29))
        .group_by(Cost.day)
        .order_by(Cost.day.desc())
    ).all()
    per_model = session.execute(
        select(Cost.kind, Cost.provider, Cost.model, func.count(), total)
        .where(Cost.day >= month_start, Cost.day <= day)
        .group_by(Cost.kind, Cost.provider, Cost.model)
        .order_by(total.desc())
    ).all()
    phase = (repo.get_setting(session, "phase") or {}).get("value") or settings.phase
    return page(
        request,
        "costs.html",
        day=day,
        spent_today=repo.spent_on(session, day),
        spent_month=repo.spent_between(session, month_start, day),
        cap=founder.effective_cap(session, settings, phase, day),
        founder_cap=founder.today_cap(session, day),
        max_cap=founder.MAX_TODAY_CAP_EUR,
        per_day=per_day,
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
