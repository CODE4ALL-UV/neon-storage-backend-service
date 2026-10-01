"""Lo que todos los servicios necesitan saber de los cursos.

Aquí no hay reglas de permisos ni respuestas HTTP: solo datos. Quién puede ver
o editar un curso lo decide course-content; esto es lo que comparten los
servicios para no repetir la misma consulta de cuatro maneras distintas.
"""

import secrets
from typing import Optional

from sqlalchemy.orm import Session

from neon_storage.models import Course, CourseEnrollment

GENERAL_TITLE = "Curso general de Code4All"
GENERAL_DESCRIPTION = (
    "El curso de Python de Code4All para todos los estudiantes, con lo que se "
    "editó antes de que cada docente tuviera sus propios cursos."
)

# Sin 0/O ni 1/I/L: el código se dicta en clase y se copia de la pizarra.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH = 6


def new_join_code(db: Session) -> str:
    """Un código de inscripción que no tenga ningún otro curso."""
    while True:
        code = "".join(secrets.choice(_ALPHABET) for _ in range(JOIN_CODE_LENGTH))
        taken = db.query(Course.id).filter(Course.join_code == code).first()
        if taken is None:
            return code


def normalize_join_code(code: Optional[str]) -> str:
    """El código tal y como lo escribe la gente: con espacios o en minúsculas."""
    return "".join((code or "").split()).upper()


def general_course(db: Session) -> Course:
    """El Curso general. Se crea si todavía no existe."""
    course = (
        db.query(Course)
        .filter(Course.is_general.is_(True))
        .order_by(Course.id)
        .first()
    )
    if course is not None:
        return course

    course = Course(
        teacher_id=None,
        title=GENERAL_TITLE,
        description=GENERAL_DESCRIPTION,
        join_code=new_join_code(db),
        is_general=True,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def is_enrolled(db: Session, course_id: int, student_id: Optional[int]) -> bool:
    if student_id is None:
        return False
    return (
        db.query(CourseEnrollment.id)
        .filter(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.student_id == student_id,
        )
        .first()
        is not None
    )
