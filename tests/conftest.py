import os
from decimal import Decimal

import pytest
from sqlalchemy import make_url, text

import scout.db.models  # noqa: F401  (registers tables on Base.metadata)
from scout.config import Settings, normalize_db_url
from scout.db.base import Base, make_engine, make_session_factory


def pytest_collection_modifyitems(config, items):
    if os.environ.get("TEST_DATABASE_URL"):
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL not set; database tests skipped")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def test_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    return normalize_db_url(url)


def assert_test_database(url: str) -> None:
    """The DB fixtures DROP and TRUNCATE every table: refuse any database whose name lacks "test" so a
    pasted production (Neon) URL can never be wiped."""
    name = make_url(url).database or ""
    if "test" not in name.lower():
        raise pytest.UsageError(
            f"refusing to drop tables in database {name!r}: TEST_DATABASE_URL must name a database "
            "containing 'test'"
        )


@pytest.fixture(scope="session")
def db_engine(test_db_url):
    assert_test_database(test_db_url)
    engine = make_engine(test_db_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    factory = make_session_factory(db_engine)
    with db_engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def settings(test_db_url) -> Settings:
    return Settings(
        _env_file=None,
        ANTHROPIC_API_KEY="sk-test",
        DATABASE_URL=test_db_url,
        daily_budget_eur=Decimal("3.00"),
    )
