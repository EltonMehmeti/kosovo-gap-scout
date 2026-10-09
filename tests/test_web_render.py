from datetime import UTC, date, datetime

from scout.clock import local_today
from scout.web.auth import cookie_value, token_matches
from scout.web.deps import local_path
from scout.web.render import md


def test_md_renders_markdown_and_escapes_html():
    out = str(md("# Title\n\n<script>alert(1)</script>\n\n| a | b |\n|---|---|\n| 1 | 2 |"))
    assert "<h1>Title</h1>" in out
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<table>" in out


def test_md_drops_javascript_links_and_handles_none():
    assert 'href="javascript:' not in str(md("[x](javascript:alert(1))"))
    assert str(md(None)) == ""


def test_cookie_value_is_stable_and_not_the_token():
    assert cookie_value("abc") == cookie_value("abc")
    assert cookie_value("abc") != cookie_value("abd")
    assert "abc" not in cookie_value("abc")
    assert token_matches("abc", "abc") and not token_matches("abc", "abd")


def test_local_path_only_allows_same_site_paths():
    assert local_path("/gaps?x=1") == "/gaps?x=1"
    for bad in (
        "//evil.com",
        "https://evil.com",
        "evil.com",
        "",
        "/\\evil.com",
        "/\t/evil.com",
        "/\n/evil.com",
    ):
        assert local_path(bad) == "/"


def test_local_today_uses_the_kosovo_date():
    # 23:30 UTC on 2026-10-09 is already 2026-10-10 in Kosovo (CEST, UTC+2)
    now = datetime(2026, 10, 9, 23, 30, tzinfo=UTC)
    assert local_today("Europe/Belgrade", now) == date(2026, 10, 10)
