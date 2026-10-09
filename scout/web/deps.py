"""Shared request helpers: DB session, templates, Kosovo's date, flash-message redirects."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from scout.clock import local_today
from scout.web.render import md

NAV = [
    ("/", "Today"),
    ("/gaps", "Gaps"),
    ("/field-checks", "Field checks"),
    ("/pipeline", "Pipeline"),
    ("/knowledge", "Knowledge"),
    ("/journal", "Journal"),
    ("/costs", "Costs"),
    ("/settings", "Settings"),
]

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters["md"] = md
templates.env.globals["NAV"] = NAV


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def local_day(request: Request) -> date:
    return local_today(request.app.state.settings.timezone)


def page(request: Request, name: str, *, status_code: int = 200, **ctx):
    ctx = {"msg": request.query_params.get("msg"), "err": request.query_params.get("err"), **ctx}
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def local_path(url: str) -> str:
    """Only same-site paths may be redirect targets (`next=` fields come from the browser)."""
    if url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return "/"


def back(url: str, *, msg: str | None = None, err: str | None = None) -> RedirectResponse:
    params = {k: v for k, v in (("msg", msg), ("err", err)) if v}
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    return RedirectResponse(url, status_code=303)
