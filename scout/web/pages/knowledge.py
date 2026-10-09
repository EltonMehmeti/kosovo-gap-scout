"""Knowledge: sectors with digests, businesses and proven models; fact search; digest editing."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout import founder
from scout.db import repo
from scout.db.models import Business, Digest, ProvenModel
from scout.founder import FounderError
from scout.web.deps import back, get_session, local_day, page

router = APIRouter()


@router.get("/knowledge", response_class=HTMLResponse)
def knowledge_page(request: Request, q: str = "", session: Session = Depends(get_session)):
    counts = dict(
        session.execute(select(Business.sector_id, func.count()).group_by(Business.sector_id)).all()
    )
    models = dict(
        session.execute(
            select(ProvenModel.sector_id, func.count()).group_by(ProvenModel.sector_id)
        ).all()
    )
    other_digests = session.scalars(
        select(Digest).where(~Digest.key.startswith("sector:")).order_by(Digest.key)
    ).all()
    facts = repo.search_facts(session, q, now=datetime.now(UTC), limit=50) if q.strip() else []
    return page(
        request,
        "knowledge.html",
        sectors=sorted(repo.list_sectors(session), key=lambda s: (-s.priority, s.slug)),
        business_counts=counts,
        model_counts=models,
        other_digests=other_digests,
        q=q,
        facts=facts,
    )


@router.get("/knowledge/sectors/{slug}", response_class=HTMLResponse)
def sector_page(slug: str, request: Request, session: Session = Depends(get_session)):
    sector = repo.get_sector(session, slug)
    if sector is None:
        raise HTTPException(status_code=404, detail="no such sector")
    return page(
        request,
        "sector.html",
        sector=sector,
        digest=session.get(Digest, f"sector:{slug}"),
        businesses=repo.list_businesses(session, slug),
        models=session.scalars(
            select(ProvenModel).where(ProvenModel.sector_id == sector.id).order_by(ProvenModel.name)
        ).all(),
        gaps=repo.list_gaps(session, sector_slugs=[slug]),
    )


@router.get("/knowledge/digests/{key}", response_class=HTMLResponse)
def digest_page(key: str, request: Request, session: Session = Depends(get_session)):
    digest = session.get(Digest, key)
    if digest is None:
        raise HTTPException(status_code=404, detail="no such digest")
    return page(request, "digest.html", digest=digest)


@router.post("/knowledge/digests/{key}")
def digest_save(
    key: str, request: Request, body_md: str = Form(""), session: Session = Depends(get_session)
):
    try:
        founder.edit_digest(session, key, body_md, today=local_day(request), now=datetime.now(UTC))
    except FounderError as e:
        return back(f"/knowledge/digests/{key}", err=str(e))
    return back(f"/knowledge/digests/{key}", msg="Saved")
