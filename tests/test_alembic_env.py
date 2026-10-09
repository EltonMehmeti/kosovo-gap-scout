"""alembic/env.py must accept a DATABASE_URL with percent-encoded characters (Minor 10)."""

from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from scout.config import get_settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def percent_url(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no .env is read
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://scout:p%40ss%25w0rd@db.example:5432/scout")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_env_accepts_percent_encoded_password_offline(percent_url, capsys):
    cfg = Config(str(ROOT / "alembic.ini"))
    command.upgrade(cfg, "head", sql=True)  # offline: renders SQL, connects to nothing
    out = capsys.readouterr().out
    assert "CREATE TABLE gaps" in out
    assert cfg.get_main_option("sqlalchemy.url").endswith("p%40ss%25w0rd@db.example:5432/scout")


def test_social_tables_are_in_the_migrations(percent_url, capsys):
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head", sql=True)
    out = capsys.readouterr().out
    assert "CREATE TABLE ads" in out and "CREATE TABLE social_cache" in out
