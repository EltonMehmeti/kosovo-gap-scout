"""Pipeline: failures to retry, tasks waiting for the next run, running tasks and past runs."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import Run, Task
from scout.founder import FounderError
from scout.web import ui
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/pipeline", response_class=HTMLResponse)
def pipeline_page(request: Request, session: Session = Depends(get_session)):
    last = repo.last_run(session)
    failed = select(Task).where(Task.status == "failed")
    return page(
        request,
        "pipeline.html",
        queue=repo.queued_tasks(session),
        running=session.scalars(
            select(Task).where(Task.status == "running").order_by(Task.id)
        ).all(),
        failed=session.scalars(failed.order_by(Task.id.desc()).limit(20)).all(),
        failed_count=session.scalar(select(func.count()).select_from(failed.subquery())) or 0,
        last=last,
        last_tasks=repo.tasks_for_run(session, last.id if last else None),
        runs=session.scalars(select(Run).order_by(Run.id.desc()).limit(14)).all(),
        profiles=founder.TASK_PROFILES,
        sectors=repo.list_sectors(session),
        next_run=ui.next_run_text(datetime.now(UTC), request.app.state.settings.timezone),
    )


def _int_or_none(raw: str, name: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise FounderError(f"{name} must be a whole number") from None


@router.post("/tasks")
def add_task(
    request: Request,
    profile: str = Form(""),
    sector: str = Form(""),
    gap_id: str = Form(""),
    theme: str = Form(""),
    priority: str = Form("70"),
    session: Session = Depends(get_session),
):
    try:
        prio = _int_or_none(priority, "priority")
        task = founder.add_task(
            session,
            profile,
            today=local_day(request),
            sector=sector.strip() or None,
            gap_id=_int_or_none(gap_id, "gap id"),
            theme=theme.strip() or None,
            priority=70 if prio is None else prio,
        )
    except FounderError as e:
        return back("/pipeline", err=str(e))
    return back("/pipeline", msg=f"Queued task #{task.id}: {ui.profile_label(task.profile)}")


@router.post("/tasks/{task_id}/retry")
def retry(task_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        task = founder.retry_task(session, task_id, today=local_day(request))
    except FounderError as e:
        return back("/pipeline", err=str(e))
    return back("/pipeline", msg=f"Task #{task.id} re-queued")
