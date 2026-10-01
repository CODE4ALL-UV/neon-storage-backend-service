"""Pasar de «un curso para todos» a «un curso por docente» sin perder nada.

La base de producción ya tiene respuestas y actividades terminadas de antes de
que existieran los cursos. Estas pruebas parten de ese esquema antiguo y
comprueban que, tras preparar la base, todo eso queda en el Curso general en
vez de quedar huérfano.
"""

import pytest
from sqlalchemy import inspect, text

from neon_storage.courses import (
    GENERAL_TITLE,
    general_course,
    new_join_code,
    normalize_join_code,
)
from neon_storage.database import Base, SessionLocal, engine
from neon_storage.models import Course
from neon_storage.schema import COURSE_SCOPED_TABLES, prepare_database

OLD_TABLES = {
    "CourseOverride": """
        CREATE TABLE "CourseOverride" (
            id INTEGER PRIMARY KEY, scope VARCHAR(20) NOT NULL,
            target_id VARCHAR(60) NOT NULL, payload TEXT NOT NULL,
            updated_by VARCHAR(100), updated_at DATETIME,
            CONSTRAINT uq_course_override UNIQUE (scope, target_id))""",
    "QuizAnswer": """
        CREATE TABLE "QuizAnswer" (
            id INTEGER PRIMARY KEY, usuario_id INTEGER, section_id VARCHAR(40) NOT NULL,
            activity VARCHAR(20) NOT NULL, question_index INTEGER NOT NULL,
            prompt VARCHAR(500) NOT NULL DEFAULT '', correct BOOLEAN NOT NULL,
            elapsed_ms INTEGER, answered_at DATETIME)""",
    "ActivityCompletion": """
        CREATE TABLE "ActivityCompletion" (
            id INTEGER PRIMARY KEY, usuario_id INTEGER, section_id VARCHAR(40) NOT NULL,
            activity VARCHAR(20) NOT NULL, completed_at DATETIME,
            CONSTRAINT uq_activity_completion UNIQUE (usuario_id, section_id, activity))""",
    "ContentReview": """
        CREATE TABLE "ContentReview" (
            id INTEGER PRIMARY KEY, section_id VARCHAR(40) NOT NULL,
            status VARCHAR(20) NOT NULL, comment TEXT NOT NULL DEFAULT '',
            director_id INTEGER, reviewed_at DATETIME,
            CONSTRAINT uq_content_review_section UNIQUE (section_id))""",
}


@pytest.fixture(autouse=True)
def _back_to_the_current_schema():
    """Deja la base con el esquema de ahora al terminar.

    Dentro del gateway todas las pruebas comparten una base. SQLite no deja
    cambiar restricciones, así que una tabla antigua que se quedara viva haría
    fallar a las pruebas que vengan después.
    """
    yield
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        for table in COURSE_SCOPED_TABLES:
            connection.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
    prepare_database()


def _old_schema_with_data():
    """La base tal y como está en producción antes de este cambio."""
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        for table in COURSE_SCOPED_TABLES:
            connection.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
        for ddl in OLD_TABLES.values():
            connection.execute(text(ddl))
        connection.execute(text(
            'INSERT INTO "CourseOverride" (scope, target_id, payload) '
            "VALUES ('section', 'm1-s1', '{\"title\": \"Editada\"}')"
        ))
        connection.execute(text(
            'INSERT INTO "QuizAnswer" (usuario_id, section_id, activity, question_index, correct) '
            "VALUES (3, 'm1-s1', 'quiz', 0, 1)"
        ))
        connection.execute(text(
            'INSERT INTO "ActivityCompletion" (usuario_id, section_id, activity) '
            "VALUES (3, 'm1-s1', 'lectura')"
        ))
        connection.execute(text(
            'INSERT INTO "ContentReview" (section_id, status) VALUES (\'m1-s1\', \'aprobado\')'
        ))


def test_old_data_ends_up_in_the_general_course():
    _old_schema_with_data()

    prepare_database()

    inspector = inspect(engine)
    db = SessionLocal()
    try:
        general = general_course(db)
        assert general.is_general
        assert general.title == GENERAL_TITLE
        assert general.teacher_id is None

        with engine.connect() as connection:
            for table in COURSE_SCOPED_TABLES:
                columns = {c["name"] for c in inspector.get_columns(table)}
                assert "course_id" in columns, table
                orphans = connection.execute(
                    text(f'SELECT count(*) FROM "{table}" WHERE course_id IS NULL')
                ).scalar()
                assigned = connection.execute(
                    text(f'SELECT count(*) FROM "{table}" WHERE course_id = :g'),
                    {"g": general.id},
                ).scalar()
                assert orphans == 0, table
                assert assigned == 1, table
    finally:
        db.close()


def test_preparing_twice_changes_nothing():
    prepare_database()
    prepare_database()

    db = SessionLocal()
    try:
        generals = db.query(Course).filter(Course.is_general.is_(True)).count()
        assert generals == 1
    finally:
        db.close()


def test_join_codes_are_short_unique_and_easy_to_dictate():
    db = SessionLocal()
    try:
        codes = {new_join_code(db) for _ in range(200)}
    finally:
        db.close()

    assert len(codes) == 200
    for code in codes:
        assert len(code) == 6
        assert not set(code) & set("0O1IL")


def test_a_code_typed_with_spaces_or_lowercase_still_matches():
    assert normalize_join_code("  ab3 k7m ") == "AB3K7M"
    assert normalize_join_code(None) == ""
