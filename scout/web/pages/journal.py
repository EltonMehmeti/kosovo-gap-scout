"""Journal: what the scout did, learned and plans, per day; founder actions appear as their own entry."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from scout.db import repo
from scout.web.deps import get_session, page

router = APIRouter()


@router.get("/journal", response_class=HTMLResponse)
def journal_page(request: Request, session: Session = Depends(get_session)):
    return page(request, "journal.html", entries=repo.latest_journal(session, limit=60))
