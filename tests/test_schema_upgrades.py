"""Las columnas que llegaron después a tablas que ya existían.

`create_all()` no toca una tabla que ya está, así que la base de quien venía
usando la app se quedaría sin las columnas nuevas. Estas pruebas parten de las
tablas tal y como eran antes y comprueban que preparar la base las pone al
día sin perder lo que ya había.
"""

import pytest
from sqlalchemy import MetaData, Table, inspect, text

from neon_storage.courses import general_course
from neon_storage.database import Base, SessionLocal, engine
from neon_storage.schema import (
    COURSE_SCOPED_TABLES,
    create_tables,
    ensure_courses,
    ensure_quiz_answer_columns,
    ensure_user_role_column,
    prepare_database,
)

OLD_USUARIO = """
    CREATE TABLE "Usuario" (
        id_usuario INTEGER PRIMARY KEY, nombre VARCHAR(100) NOT NULL,
        correo VARCHAR(100) NOT NULL UNIQUE, password VARCHAR(255) NOT NULL,
        fecha_registro DATE, tipo_discapacidad INTEGER)"""

OLD_QUIZ_ANSWER = """
    CREATE TABLE "QuizAnswer" (
        id INTEGER PRIMARY KEY, usuario_id INTEGER, section_id VARCHAR(40) NOT NULL,
        activity VARCHAR(20) NOT NULL, question_index INTEGER NOT NULL,
        prompt VARCHAR(500) NOT NULL DEFAULT '', correct BOOLEAN NOT NULL,
        answered_at DATETIME)"""


def _drop_everything():
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        for table in COURSE_SCOPED_TABLES:
            Table(table, MetaData()).drop(connection, checkfirst=True)


def _columns(table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


@pytest.fixture(autouse=True)
def _back_to_the_current_schema():
    """Deja la base con el esquema de ahora al terminar.

    Dentro del gateway todas las pruebas comparten una base: una tabla antigua
    que se quedara viva haría fallar a las que vengan después.
    """
    yield
    _drop_everything()
    prepare_database()


def test_old_accounts_get_a_role_and_a_photo_column():
    _drop_everything()
    with engine.begin() as connection:
        connection.execute(text(OLD_USUARIO))
        connection.execute(text(
            'INSERT INTO "Usuario" (nombre, correo, password) '
            "VALUES ('Ana', 'ana@example.com', 'x')"
        ))

    prepare_database()

    assert {"rol", "foto_path"} <= _columns("Usuario")
    with engine.connect() as connection:
        row = connection.execute(
            text('SELECT nombre, rol, foto_path FROM "Usuario" WHERE correo = :correo'),
            {"correo": "ana@example.com"},
        ).one()
    # Quien ya tenía cuenta sigue ahí, y como estudiante, que es lo que era.
    assert tuple(row) == ("Ana", "estudiante", None)


def test_old_answers_get_the_time_column_empty_and_not_as_zero():
    _drop_everything()
    with engine.begin() as connection:
        connection.execute(text(OLD_QUIZ_ANSWER))
        connection.execute(text(
            'INSERT INTO "QuizAnswer" (usuario_id, section_id, activity, question_index, correct) '
            "VALUES (3, 'm1-s1', 'quiz', 0, 1)"
        ))

    prepare_database()

    assert {"elapsed_ms", "course_id"} <= _columns("QuizAnswer")
    with engine.connect() as connection:
        elapsed = connection.execute(text('SELECT elapsed_ms FROM "QuizAnswer"')).scalar_one()
    assert elapsed is None


def test_a_database_that_is_up_to_date_is_left_as_it_is():
    prepare_database()
    before = {table: _columns(table) for table in ("Usuario", "QuizAnswer")}

    ensure_user_role_column()
    ensure_quiz_answer_columns()

    assert {table: _columns(table) for table in before} == before


def test_the_column_upgrades_do_nothing_on_an_empty_database():
    _drop_everything()

    ensure_user_role_column()
    ensure_quiz_answer_columns()

    # Ni fallan ni se inventan las tablas: crearlas es cosa de create_all().
    assert not {"Usuario", "QuizAnswer"} & set(inspect(engine).get_table_names())


def test_moving_to_courses_skips_the_tables_that_are_not_there_yet():
    _drop_everything()
    create_tables()
    with engine.begin() as connection:
        connection.execute(text('DROP TABLE "ContentReview"'))

    ensure_courses()

    assert "ContentReview" not in inspect(engine).get_table_names()
    db = SessionLocal()
    try:
        assert general_course(db).is_general
    finally:
        db.close()
