"""Home: what needs the founder, four numbers, the last run and the latest brief."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import Gap, Task
from scout.web import ui
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def today_page(request: Request, session: Session = Depends(get_session)):
    settings = request.app.state.settings
    day = local_day(request)
    now = datetime.now(UTC)
    now_local = now.astimezone(ZoneInfo(settings.timezone))
    brief = repo.latest_brief(session)
    read_id = (repo.get_setting(session, "brief_read") or {}).get("id")
    phase = (repo.get_setting(session, "phase") or {}).get("value") or settings.phase

    def count(stmt) -> int:
        return session.scalar(stmt) or 0

    return page(
        request,
        "today.html",
        session=session,
        brief=brief,
        unread=brief is not None and brief.id != read_id,
        last=repo.last_run(session),
        spent_today=repo.spent_on(session, day),
        spent_month=repo.spent_between(session, day.replace(day=1), day),
        cap=founder.effective_cap(session, settings, phase, day),
        open_checks=len(repo.open_field_checks(session)),
        failed=count(select(func.count()).select_from(Task).where(Task.status == "failed")),
        open_gaps=count(
            select(func.count()).select_from(Gap).where(Gap.status.in_(ui.OPEN_GAP_STATUSES))
        ),
        greeting=ui.greeting(now_local),
        now_local=now_local,
        next_run=ui.next_run_text(now, settings.timezone),
    )


@router.post("/brief/{brief_id}/read")
def mark_read(brief_id: int, session: Session = Depends(get_session)):
    repo.set_setting(session, "brief_read", {"id": brief_id})
    return back("/")
