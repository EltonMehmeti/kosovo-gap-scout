"""Shared request helpers: DB session, templates, Kosovo's date, flash-message redirects, and the
sidebar's badges."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scout.clock import local_today
from scout.db import repo
from scout.db.models import Task
from scout.web import ui
from scout.web.render import md

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
BARE_PAGES = frozenset({"login.html", "error.html"})  # no sidebar, so no badges to compute


def _asset_version() -> str:
    """Changes whenever a served asset changes, so browsers drop their day-long cached copy."""
    digest = hashlib.sha256()
    for name in ("app.css", "app.js", "icons.svg"):
        digest.update((STATIC_DIR / name).read_bytes())
    return digest.hexdigest()[:10]


ASSET_VERSION = _asset_version()


@pass_context
def _when(ctx, value) -> str:
    request = ctx.get("request")
    tz = request.app.state.settings.timezone if request is not None else ui.DEFAULT_TZ
    return ui.human_date(value, local_today(tz), tz)


templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters.update(md=md, eur=ui.eur, pct=ui.pct, iso=ui.iso, when=_when)
templates.env.globals.update(
    ASSET_VERSION=ASSET_VERSION,
    SECTIONS=ui.SECTIONS,
    SECTION_TABS=ui.SECTION_TABS,
    SCORE_PARTS=ui.SCORE_PARTS,
    active_section=ui.active_section,
    status_label=ui.status_label,
    task_label=ui.task_label,
    run_label=ui.run_label,
    flag_label=ui.flag_label,
    phase_info=ui.phase_info,
    profile_label=ui.profile_label,
    presence_label=ui.presence_label,
    task_target=ui.task_target,
    score_band=ui.score_band,
)


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def local_day(request: Request) -> date:
    return local_today(request.app.state.settings.timezone)


def nav_badges(session: Session) -> dict[str, int]:
    """Counts shown next to the sidebar sections; 0 hides the badge."""
    brief = repo.latest_brief(session)
    read_id = (repo.get_setting(session, "brief_read") or {}).get("id")
    failed = session.scalar(select(func.count()).select_from(Task).where(Task.status == "failed"))
    return {
        "home": int(brief is not None and brief.id != read_id),
        "gaps": len(repo.open_field_checks(session)),
        "activity": failed or 0,
    }


def _shell(request: Request, session: Session | None) -> dict:
    """Badges and the phase pill for the sidebar. A failure here never fails the page."""
    own = session is None
    s = request.app.state.session_factory() if own else session
    try:
        phase = (repo.get_setting(s, "phase") or {}).get(
            "value"
        ) or request.app.state.settings.phase
        tz = request.app.state.settings.timezone
        next_run = ui.next_run_text(datetime.now(UTC), tz)
        return {"nav_badges": nav_badges(s), "nav_phase": phase, "nav_next": next_run}
    except Exception:
        log.warning("sidebar badges unavailable", exc_info=True)
        if not own:
            s.rollback()
        return {"nav_badges": {}, "nav_phase": None, "nav_next": None}
    finally:
        if own:
            s.close()


def page(
    request: Request,
    name: str,
    *,
    status_code: int = 200,
    session: Session | None = None,
    **ctx,
):
    base = {"msg": request.query_params.get("msg"), "err": request.query_params.get("err")}
    if name in BARE_PAGES:
        base |= {"nav_badges": {}, "nav_phase": None, "nav_next": None}
    else:
        base |= _shell(request, session)
    return templates.TemplateResponse(request, name, {**base, **ctx}, status_code=status_code)


def local_path(url: str) -> str:
    """Only same-site paths may be redirect targets (`next=` fields come from the browser)."""
    if (
        url.startswith("/")
        and not url.startswith("//")
        and not any(c in url for c in "\\\t\r\n")  # browsers drop tab/CR/LF: "/\t/x" is "//x"
    ):
        return url
    return "/"


def back(url: str, *, msg: str | None = None, err: str | None = None) -> RedirectResponse:
    params = {k: v for k, v in (("msg", msg), ("err", err)) if v}
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    return RedirectResponse(url, status_code=303)
