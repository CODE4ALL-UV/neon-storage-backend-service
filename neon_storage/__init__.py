"""Persistencia de Code4All en Neon (PostgreSQL).

No es un servicio con rutas propias: es la capa de datos que comparten los
microservicios. Lo que se usa desde fuera:

    from neon_storage import get_db, prepare_database
    from neon_storage.models import Usuario, CourseOverride, ...
"""

from neon_storage.database import Base, SessionLocal, engine, get_db
from neon_storage.schema import prepare_database

__all__ = ["Base", "SessionLocal", "engine", "get_db", "prepare_database"]
