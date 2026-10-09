from decimal import Decimal

from scout.config import Settings, normalize_db_url


def test_normalize_db_url_keeps_query():
    url = "postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    assert normalize_db_url(url) == (
        "postgresql+psycopg://u:p@ep-x.eu-central-1.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )


def test_normalize_db_url_handles_postgres_scheme_and_idempotent():
    assert normalize_db_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_db_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


def test_settings_read_env(monkeypatch):
    for k in (
        "SCOUT_PHASE",
        "SCOUT_DAILY_BUDGET_EUR",
        "SCOUT_RUN_MAX_MINUTES",
        "SCOUT_USD_TO_EUR",
        "SCOUT_TIMEZONE",
        "SCOUT_DIRECTOR_REVIEW",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("SCOUT_DAILY_BUDGET_EUR", "1.50")
    monkeypatch.setenv("SCOUT_PHASE", "verification")
    s = Settings(_env_file=None)
    assert s.anthropic_api_key == "sk-test"
    assert s.database_url == "postgresql+psycopg://u:p@h/db"
    assert s.daily_budget_eur == Decimal("1.50")
    assert s.phase == "verification"
    assert s.timezone == "Europe/Belgrade"
    assert s.director_review is True


def test_anthropic_key_is_optional_for_the_dashboard(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DASHBOARD_TOKEN", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    s = Settings(_env_file=None)
    assert s.anthropic_api_key == "" and s.dashboard_token is None


def test_run_once_refuses_without_an_anthropic_key(monkeypatch):
    import pytest

    from scout.director.run import run_once

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        run_once(s, session_factory=lambda: None)
