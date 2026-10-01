import pytest

from neon_storage.database import _clean_database_url

NEON = "postgresql://user:pass@ep-demo-123.us-east-2.aws.neon.tech/neondb?sslmode=require"

# Lo que debe quedar: la misma cadena, con el driver dicho explícitamente.
CLEAN = NEON.replace("postgresql://", "postgresql+psycopg2://", 1)


def test_strips_quotes_dragged_from_env_file():
    assert _clean_database_url(f'"{NEON}"') == CLEAN
    assert _clean_database_url(f"'{NEON}'") == CLEAN


def test_joins_a_url_split_across_lines():
    broken = NEON[:30] + "\n  " + NEON[30:]

    assert _clean_database_url(broken) == CLEAN


def test_rewrites_the_old_postgres_scheme():
    assert _clean_database_url(NEON.replace("postgresql://", "postgres://", 1)) == CLEAN


def test_names_the_installed_driver_so_sqlalchemy_2_1_does_not_look_for_another():
    assert _clean_database_url(NEON).startswith("postgresql+psycopg2://")


def test_keeps_a_driver_that_was_already_chosen():
    chosen = NEON.replace("postgresql://", "postgresql+psycopg://", 1)

    assert _clean_database_url(chosen) == chosen


def test_missing_url_explains_where_to_set_it():
    with pytest.raises(ValueError, match="Falta la variable DATABASE_URL"):
        _clean_database_url(None)


def test_only_the_tail_of_the_url_says_so():
    with pytest.raises(ValueError, match="solo trae la parte final"):
        _clean_database_url("?sslmode=require")
