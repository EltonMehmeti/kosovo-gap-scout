# tests/test_web_shell.py
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from scout.db import repo
from scout.db.base import make_session_factory
from scout.web import deps, ui
from scout.web.app import create_app

pytestmark = pytest.mark.db


def _anon(settings, db_engine):
    app = create_app(settings, make_session_factory(db_engine))
    return TestClient(app, base_url="https://testserver")


def test_static_files_are_public_and_cached(db_session, db_engine, settings):
    c = _anon(settings, db_engine)
    for path in (
        "/static/app.css",
        "/static/app.js",
        "/static/icons.svg",
        "/static/fonts/inter-latin-wght-normal.woff2",
    ):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 200, path
        assert r.headers["cache-control"] == "public, max-age=86400", path
    assert "text/css" in c.get("/static/app.css").headers["content-type"]
    assert c.get("/static/nope.css").status_code == 404


def test_only_the_static_prefix_is_open(db_session, db_engine, settings):
    c = _anon(settings, db_engine)
    for path in ("/staticx", "/static", "/staticapp.css"):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login", path


def test_login_page_is_styled_and_has_no_navigation(db_session, db_engine, settings):
    html = _anon(settings, db_engine).get("/login").text
    assert re.fullmatch(r"[0-9a-f]{10}", deps.ASSET_VERSION)
    assert f"/static/app.css?v={deps.ASSET_VERSION}" in html
    assert f"/static/app.js?v={deps.ASSET_VERSION}" in html
    assert 'aria-label="Main"' not in html and "Dashboard token" in html


def test_shell_has_five_sections_and_marks_the_current_one(web):
    html = web.get("/journal").text
    assert '<nav class="side-nav" aria-label="Main">' in html
    for label in ("Home", "Gaps", "Activity", "Knowledge", "Settings"):
        assert f"<span>{label}</span>" in html
    assert '<a href="/pipeline" aria-current="page">' in html
    assert '<a href="/" aria-current="page">' not in html
    assert "Foundation" in html  # phase pill


def test_every_section_icon_exists_in_the_sprite():
    sprite = (deps.STATIC_DIR / "icons.svg").read_text()
    for s in ui.SECTIONS:
        assert f'id="i-{s.icon}"' in sprite, s.icon


def test_nav_badges_count_what_needs_attention(web, db_session):
    assert "data-badge=" not in web.get("/journal").text
    repo.save_brief(db_session, run_id=None, day=date(2026, 10, 9), markdown="b")
    repo.add_field_check(db_session, gap_id=None, question="q?", why="w", due=date(2026, 10, 11))
    t = repo.enqueue_task(db_session, profile="news-scan", payload={}, priority=40)
    t.status = "failed"
    db_session.commit()
    html = web.get("/journal").text
    for key in ("home", "gaps", "activity"):
        assert re.search(rf'data-badge="{key}"[^>]*>1<', html), key


def test_badges_never_break_a_page(web, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(repo, "open_field_checks", boom)
    r = web.get("/journal")
    assert r.status_code == 200 and "data-badge=" not in r.text


def test_flash_messages_render_as_escaped_toasts(web):
    ok = web.get("/journal", params={"msg": "<b>Saved</b>"}).text
    assert "data-toast" in ok and "&lt;b&gt;Saved&lt;/b&gt;" in ok and "data-sticky" not in ok
    err = web.get("/journal", params={"err": "Nope"}).text
    assert 'role="alert" data-toast data-sticky' in err and "Nope" in err


def test_error_page_uses_the_bare_layout(web):
    r = web.get("/gaps/99999999999")
    assert r.status_code == 400 and "out of range or not allowed" in r.text
    assert 'aria-label="Main"' not in r.text
