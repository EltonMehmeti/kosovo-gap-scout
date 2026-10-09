"""Field checks: the founder's ≤ 5 open questions; an answer becomes a fact and re-queues verify-gap."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import FieldCheck
from scout.founder import FounderError
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/field-checks", response_class=HTMLResponse)
def field_checks_page(request: Request, session: Session = Depends(get_session)):
    answered = session.scalars(
        select(FieldCheck)
        .where(FieldCheck.status != "open")
        .order_by(FieldCheck.answered_at.desc().nulls_last(), FieldCheck.id.desc())
        .limit(10)
    ).all()
    gaps = {g.id: g for g in repo.list_gaps(session)}
    return page(
        request,
        "field_checks.html",
        open_checks=repo.open_field_checks(session),
        answered=answered,
        gaps=gaps,
    )


@router.post("/field-checks/{check_id}/answer")
def answer(
    check_id: int, request: Request, answer: str = Form(""), session: Session = Depends(get_session)
):
    try:
        fc = founder.answer_field_check(
            session, check_id, answer, today=local_day(request), now=datetime.now(UTC)
        )
    except FounderError as e:
        return back("/field-checks", err=str(e))
    return back("/field-checks", msg="Answered; verify-gap queued" if fc.gap_id else "Answered")
