"""La sesión que reciben las rutas y la consulta de inscripción que comparten.

Cada petición abre una sesión con la base y tiene que cerrarla siempre, también
cuando la petición falla: si no, Neon se queda sin conexiones libres. Y saber
si un estudiante está en un curso es la pregunta que hacen varios servicios,
así que tiene que responder lo mismo para todos.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from neon_storage import database
from neon_storage.courses import is_enrolled, new_join_code
from neon_storage.database import SessionLocal, get_db
from neon_storage.models import Course, CourseEnrollment
from neon_storage.schema import prepare_database


class _ClosingSpy:
    """Una sesión que solo apunta si la cerraron."""

    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_a_request_gets_a_working_session_with_the_database():
    sessions = get_db()
    db = next(sessions)
    try:
        assert isinstance(db, Session)
        assert db.execute(text("SELECT 1")).scalar() == 1
    finally:
        sessions.close()


def test_the_session_is_closed_when_the_request_ends(monkeypatch):
    spy = _ClosingSpy()
    monkeypatch.setattr(database, "SessionLocal", lambda: spy)

    sessions = get_db()
    assert next(sessions) is spy
    assert spy.closed is False

    with pytest.raises(StopIteration):
        next(sessions)
    assert spy.closed is True


def test_the_session_is_closed_even_if_the_request_fails(monkeypatch):
    spy = _ClosingSpy()
    monkeypatch.setattr(database, "SessionLocal", lambda: spy)

    sessions = get_db()
    next(sessions)
    with pytest.raises(RuntimeError):
        sessions.throw(RuntimeError("la ruta falló"))

    assert spy.closed is True


@pytest.fixture
def course_with_a_student():
    prepare_database()
    db = SessionLocal()
    course = Course(teacher_id=None, title="Python", join_code=new_join_code(db))
    db.add(course)
    db.flush()
    db.add(CourseEnrollment(course_id=course.id, student_id=41))
    db.commit()
    try:
        yield db, course
    finally:
        db.query(CourseEnrollment).filter(CourseEnrollment.course_id == course.id).delete()
        db.delete(course)
        db.commit()
        db.close()


def test_a_student_is_enrolled_only_where_they_joined(course_with_a_student):
    db, course = course_with_a_student

    assert is_enrolled(db, course.id, 41) is True
    assert is_enrolled(db, course.id, 42) is False
    assert is_enrolled(db, course.id + 1000, 41) is False


def test_without_an_account_nobody_is_enrolled(course_with_a_student):
    db, course = course_with_a_student

    assert is_enrolled(db, course.id, None) is False
