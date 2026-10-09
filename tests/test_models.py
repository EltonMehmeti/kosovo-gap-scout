import pytest
from sqlalchemy import inspect

pytestmark = pytest.mark.db

EXPECTED_TABLES = {
    "sources",
    "digests",
    "sectors",
    "businesses",
    "proven_models",
    "gaps",
    "gap_assessments",
    "field_checks",
    "facts",
    "tasks",
    "runs",
    "costs",
    "journal",
    "scorecard",
    "app_chart_snapshots",
    "briefs",
    "settings",
}


def test_all_tables_exist(db_engine):
    names = set(inspect(db_engine).get_table_names())
    assert EXPECTED_TABLES <= names


def test_facts_hash_is_unique(db_session):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.exc import IntegrityError

    from scout.db.models import Fact

    now = datetime.now(UTC)
    kwargs = dict(
        hash="h1",
        entity_type="sector",
        entity_key="pets",
        claim="c",
        confidence=0.5,
        source_name="web",
        observed_at=now,
        expires_at=now + timedelta(days=1),
    )
    db_session.add(Fact(**kwargs))
    db_session.commit()
    db_session.add(Fact(**kwargs))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
