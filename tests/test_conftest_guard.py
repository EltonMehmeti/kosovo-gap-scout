import pytest

from tests.conftest import assert_test_database


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://scout:scout@localhost:55432/scout",
        "postgresql+psycopg://u:p@ep-x.eu-central-1.aws.neon.tech/neondb?sslmode=require",
        "postgresql+psycopg://u:p@test-host.example/prod",  # "test" in the host is not enough
    ],
)
def test_refuses_to_drop_a_database_whose_name_lacks_test(url):
    with pytest.raises(pytest.UsageError, match="refusing"):
        assert_test_database(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://scout:scout@localhost:55432/scout_test",
        "postgresql+psycopg://scout:scout@localhost:55432/scout_test_final",
        "postgresql+psycopg://u:p@ep-x.neon.tech/TEST_db?sslmode=require",
    ],
)
def test_accepts_test_databases(url):
    assert_test_database(url)
