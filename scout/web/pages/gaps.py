"""Gaps board: status columns (a filter on phones), detail, and the founder's buttons."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import FieldCheck, GapAssessment, ProvenModel
from scout.founder import FounderError
from scout.web import ui
from scout.web.deps import back, get_session, local_day, local_path, page

router = APIRouter()
BOARD_COLUMNS = ("candidate", "verifying", "verified", "parked")  # Rejected sits below, collapsed


@router.get("/gaps", response_class=HTMLResponse)
def gaps_page(request: Request, status: str = "", session: Session = Depends(get_session)):
    all_gaps = repo.list_gaps(session)
    columns = [(st, [g for g in all_gaps if g.status == st]) for st in BOARD_COLUMNS]
    if status not in BOARD_COLUMNS:  # phones show one column: default to the first non-empty one
        status = next((st for st, items in columns if items), BOARD_COLUMNS[0])
    return page(
        request,
        "gaps.html",
        columns=columns,
        rejected=[g for g in all_gaps if g.status == "killed"],
        selected=status,
        total=len(all_gaps),
        sectors={s.id: s for s in repo.list_sectors(session)},
        finalists=set(founder.finalists(session)),
        flagged=set(founder.flagged(session)),
    )


@router.get("/gaps/{gap_id}", response_class=HTMLResponse)
def gap_detail(gap_id: int, request: Request, session: Session = Depends(get_session)):
    gap = repo.get_gap(session, gap_id)
    if gap is None:
        raise HTTPException(status_code=404, detail="no such gap")
    assessments = session.scalars(
        select(GapAssessment)
        .where(GapAssessment.gap_id == gap_id)
        .order_by(GapAssessment.id.desc())
        .limit(5)
    ).all()
    checks = session.scalars(
        select(FieldCheck).where(FieldCheck.gap_id == gap_id).order_by(FieldCheck.id.desc())
    ).all()
    model = session.get(ProvenModel, gap.proven_model_id) if gap.proven_model_id else None
    sector = next((s for s in repo.list_sectors(session) if s.id == gap.sector_id), None)
    return page(
        request,
        "gap.html",
        gap=gap,
        sector=sector,
        model=model,
        assessments=assessments,
        checks=checks,
        is_finalist=gap.id in founder.finalists(session),
        is_flagged=gap.id in founder.flagged(session),
    )


@router.post("/gaps/{gap_id}/status")
def gap_status(
    gap_id: int,
    request: Request,
    action: str = Form(""),
    next: str = Form("/gaps"),
    session: Session = Depends(get_session),
):
    try:
        gap = founder.set_gap_status(
            session, gap_id, action, today=local_day(request), now=datetime.now(UTC)
        )
    except FounderError as e:
        return back(local_path(next), err=str(e))
    return back(local_path(next), msg=f"{gap.title}: {ui.status_label(gap.status).text}")


@router.post("/gaps/{gap_id}/flag")
def gap_flag(
    gap_id: int,
    request: Request,
    unflag: str = Form(""),
    next: str = Form("/gaps"),
    session: Session = Depends(get_session),
):
    try:
        founder.flag_gap(session, gap_id, today=local_day(request), unflag=unflag == "1")
    except FounderError as e:
        return back(local_path(next), err=str(e))
    return back(
        local_path(next),
        msg="Check cancelled"
        if unflag == "1"
        else "Check requested — the scout re-checks it next run",
    )


@router.post("/gaps/{gap_id}/finalist")
def gap_finalist(
    gap_id: int,
    request: Request,
    next: str = Form("/gaps"),
    session: Session = Depends(get_session),
):
    try:
        ids = founder.toggle_finalist(session, gap_id, today=local_day(request))
    except FounderError as e:
        return back(local_path(next), err=str(e))
    return back(
        local_path(next), msg="Added to finalists" if gap_id in ids else "Removed from finalists"
    )
