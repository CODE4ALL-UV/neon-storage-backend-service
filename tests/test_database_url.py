import pytest

from neon_storage.database import _clean_database_url

NEON = "postgresql://user:pass@ep-demo-123.us-east-2.aws.neon.tech/neondb?sslmode=require"


def test_strips_quotes_dragged_from_env_file():
    assert _clean_database_url(f'"{NEON}"') == NEON
    assert _clean_database_url(f"'{NEON}'") == NEON


def test_joins_a_url_split_across_lines():
    broken = NEON[:30] + "\n  " + NEON[30:]

    assert _clean_database_url(broken) == NEON


def test_rewrites_the_old_postgres_scheme():
    assert _clean_database_url(NEON.replace("postgresql://", "postgres://", 1)) == NEON


def test_missing_url_explains_where_to_set_it():
    with pytest.raises(ValueError, match="Falta la variable DATABASE_URL"):
        _clean_database_url(None)


def test_only_the_tail_of_the_url_says_so():
    with pytest.raises(ValueError, match="solo trae la parte final"):
        _clean_database_url("?sslmode=require")
