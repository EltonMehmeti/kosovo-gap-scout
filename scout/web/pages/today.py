"""Today: the latest brief and a one-line status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from scout.db import repo
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def today_page(request: Request, session: Session = Depends(get_session)):
    day = local_day(request)
    brief = repo.latest_brief(session)
    read_id = (repo.get_setting(session, "brief_read") or {}).get("id")
    return page(
        request,
        "today.html",
        brief=brief,
        unread=brief is not None and brief.id != read_id,
        last=repo.last_run(session),
        spent_today=repo.spent_on(session, day),
        spent_month=repo.spent_between(session, day.replace(day=1), day),
        queued=len(repo.queued_tasks(session)),
        open_checks=len(repo.open_field_checks(session)),
    )


@router.post("/brief/{brief_id}/read")
def mark_read(brief_id: int, session: Session = Depends(get_session)):
    repo.set_setting(session, "brief_read", {"id": brief_id})
    return back("/")
