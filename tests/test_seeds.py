import pytest

from scout.db import repo
from scout.seeds import CULTURE_THEMES, SECTORS, seed_all

pytestmark = pytest.mark.db


def test_seed_is_idempotent(db_session):
    first = seed_all(db_session)
    assert first["sectors"] == len(SECTORS) == 24 and first["themes"] == len(CULTURE_THEMES) == 10
    assert seed_all(db_session)["sectors"] == 0
    assert repo.get_digest(db_session, "country") and not repo.list_digests(db_session, "culture:")
    assert repo.get_sector(db_session, "home-services").priority == 1
    assert repo.get_setting(db_session, "culture_themes") == [slug for slug, _ in CULTURE_THEMES]
