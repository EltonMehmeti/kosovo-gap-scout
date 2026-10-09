import pytest
from fastapi.testclient import TestClient

from scout.db import repo
from scout.db.base import make_session_factory
from scout.web.app import create_app

pytestmark = pytest.mark.db


def _client(settings, db_engine, **overrides):
    s = settings.model_copy(update=overrides)
    return TestClient(create_app(s, make_session_factory(db_engine)), base_url="https://testserver")


def test_healthz_is_open_and_pages_need_login(db_session, db_engine, settings):
    c = _client(settings, db_engine)
    assert c.get("/healthz").text == "ok"
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert c.get("/login").status_code == 200


def test_wrong_token_is_refused_without_a_cookie(db_session, db_engine, settings):
    c = _client(settings, db_engine)
    r = c.post("/login", data={"token": "nope"}, follow_redirects=False)
    assert r.status_code == 401 and "set-cookie" not in r.headers
    assert "Wrong token" in r.text


def test_login_sets_a_locked_down_cookie_and_logout_clears_it(db_session, db_engine, settings):
    c = _client(settings, db_engine)
    r = c.post("/login", data={"token": "test-dashboard-token"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "scout_auth=" in cookie and "httponly" in cookie
    assert "samesite=lax" in cookie and "secure" in cookie
    assert "test-dashboard-token" not in cookie
    assert c.get("/").status_code == 200
    c.post("/logout")
    assert c.get("/", follow_redirects=False).status_code == 303


def test_forged_cookie_is_refused(db_session, db_engine, settings):
    c = _client(settings, db_engine)
    c.cookies.set("scout_auth", "0" * 64)
    assert c.get("/", follow_redirects=False).status_code == 303


def test_unset_token_locks_the_dashboard(db_session, db_engine, settings):
    c = _client(settings, db_engine, dashboard_token=None)
    assert c.get("/").status_code == 503
    assert c.post("/login", data={"token": ""}).status_code == 503
    assert c.get("/healthz").status_code == 200


def test_short_token_locks_like_an_unset_one(db_session, db_engine, settings):
    c = _client(settings, db_engine, dashboard_token="x" * 15)
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 503 and "at least 16 characters" in r.text
    assert c.post("/login", data={"token": "x" * 15}).status_code == 503
    assert c.get("/healthz").status_code == 200


def test_sixteen_character_token_works(db_session, db_engine, settings):
    c = _client(settings, db_engine, dashboard_token="x" * 16)
    r = c.post("/login", data={"token": "x" * 16}, follow_redirects=False)
    assert r.status_code == 303
    assert c.get("/").status_code == 200


def test_security_headers_on_every_response(web):
    for r in (web.get("/"), web.get("/healthz"), web.get("/nope")):
        assert r.headers["content-security-policy"] == "img-src 'self' data:"
        assert r.headers["referrer-policy"] == "no-referrer"
    assert '<meta name="referrer" content="no-referrer">' in web.get("/").text


def test_security_headers_also_on_locked_and_login_redirects(db_session, db_engine, settings):
    for c in (_client(settings, db_engine), _client(settings, db_engine, dashboard_token=None)):
        r = c.get("/", follow_redirects=False)
        assert r.headers["referrer-policy"] == "no-referrer"
        assert r.headers["content-security-policy"] == "img-src 'self' data:"


def test_external_image_is_escaped_as_before_and_csp_blocks_loading_it(web, db_session):
    from datetime import date

    repo.save_brief(
        db_session, run_id=None, day=date(2026, 10, 9), markdown="![x](https://evil.example/p.png)"
    )
    r = web.get("/")
    assert "evil.example" in r.text
    assert r.headers["content-security-policy"] == "img-src 'self' data:"


def test_today_with_an_empty_database(web):
    r = web.get("/")
    assert r.status_code == 200 and "No brief yet" in r.text


def test_today_renders_the_brief_and_mark_read(web, db_session):
    from datetime import date

    b = repo.save_brief(
        db_session, run_id=None, day=date(2026, 10, 9), markdown="# Big day\n\n<script>x</script>"
    )
    r = web.get("/")
    assert "<h1>Big day</h1>" in r.text and "&lt;script&gt;" in r.text and "New" in r.text
    r = web.post(f"/brief/{b.id}/read", follow_redirects=False)
    assert r.status_code == 303
    db_session.expire_all()
    assert repo.get_setting(db_session, "brief_read") == {"id": b.id}
    assert 'new-brief">New' not in web.get("/").text
