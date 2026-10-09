"""Settings: phase, sector priorities, finalists and verify requests; read-only env settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.director.planner import PHASES
from scout.founder import FounderError
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request, session: Session = Depends(get_session)):
    settings = request.app.state.settings

    def gaps_for(ids: list[int]):
        return [g for g in (repo.get_gap(session, i) for i in ids) if g is not None]

    return page(
        request,
        "settings.html",
        phase=(repo.get_setting(session, "phase") or {}).get("value") or settings.phase,
        phases=PHASES,
        sectors=sorted(repo.list_sectors(session), key=lambda s: (-s.priority, s.slug)),
        finalist_gaps=gaps_for(founder.finalists(session)),
        flagged_gaps=gaps_for(founder.flagged(session)),
        env={
            "SCOUT_DAILY_BUDGET_EUR": settings.daily_budget_eur,
            "SCOUT_TIMEZONE": settings.timezone,
            "SCOUT_DIRECTOR_REVIEW": settings.director_review,
            "Google Places key": "set" if settings.google_places_api_key else "missing",
            "Apify token": "set" if settings.apify_token else "missing",
        },
    )


@router.post("/settings/phase")
def set_phase(request: Request, phase: str = Form(""), session: Session = Depends(get_session)):
    try:
        founder.set_phase(session, phase, today=local_day(request))
    except FounderError as e:
        return back("/settings", err=str(e))
    return back("/settings", msg=f"Phase: {phase}")


@router.post("/settings/sector-priority")
def set_priority(
    request: Request,
    slug: str = Form(""),
    priority: str = Form(""),
    session: Session = Depends(get_session),
):
    try:
        try:
            value = int(priority.strip())
        except ValueError:
            raise FounderError("priority must be a whole number from 0 to 100") from None
        founder.set_sector_priority(session, slug, value, today=local_day(request))
    except FounderError as e:
        return back("/settings", err=str(e))
    return back("/settings", msg=f"{slug} priority: {value}")
