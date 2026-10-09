"""The founder's dashboard (spec B11): server-rendered pages over the database the scout writes.
Forms post and redirect back (303). There is no JavaScript framework and no API surface."""

from __future__ import annotations

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import DataError

from scout.config import Settings
from scout.web import auth
from scout.web.deps import STATIC_DIR, page
from scout.web.pages import (
    costs,
    field_checks,
    gaps,
    journal,
    knowledge,
    pipeline,
    settings_page,
    today,
)

LOCKED = (
    "DASHBOARD_TOKEN is not set or too short; the dashboard is locked. "
    f"The token must be at least {auth.MIN_TOKEN_LENGTH} characters."
)


def create_app(settings: Settings, session_factory) -> FastAPI:
    app = FastAPI(title="Kosovo Gap Scout", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.session_factory = session_factory

    @app.middleware("http")
    async def require_login(request: Request, call_next):
        path = request.url.path
        if path.startswith(auth.STATIC_PREFIX):
            response = await call_next(request)
            if response.status_code == 200:  # asset URLs carry ?v=<hash>, so a day is safe
                response.headers["Cache-Control"] = "public, max-age=86400"
            return response
        if path in auth.OPEN_PATHS:
            return await call_next(request)
        token = auth.usable_token(settings)
        if token is None:
            return PlainTextResponse(LOCKED, status_code=503)
        if not auth.is_logged_in(request, token):
            return RedirectResponse("/login", status_code=303)
        return await call_next(request)

    @app.middleware("http")  # registered last, so outermost: covers redirects and 503s too
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        # Brief markdown can embed external images; never fetch them and never send a Referer.
        response.headers["Content-Security-Policy"] = "img-src 'self' data:"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(DataError)
    def bad_value(request: Request, exc: DataError):
        # Out-of-range integers and NUL bytes are rejected by Postgres: the caller's mistake, not ours.
        return page(
            request,
            "error.html",
            status_code=400,
            message="That value is out of range or not allowed.",
        )

    @app.get("/healthz")
    def healthz():
        return PlainTextResponse("ok")

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return page(request, "login.html")

    @app.post("/login")
    def login(request: Request, token: str = Form("")):
        expected = auth.usable_token(settings)
        if expected is None:
            return PlainTextResponse(LOCKED, status_code=503)
        if not auth.token_matches(token, expected):
            return page(request, "login.html", status_code=401, err="Wrong token.")
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(
            auth.COOKIE,
            auth.cookie_value(expected),
            max_age=auth.MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=auth.is_https(request),
        )
        return resp

    @app.post("/logout")
    def logout():
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(auth.COOKIE)
        return resp

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    for module in (today, gaps, field_checks, pipeline, knowledge, journal, costs, settings_page):
        app.include_router(module.router)
    return app
