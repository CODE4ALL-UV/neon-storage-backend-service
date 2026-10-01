"""Dejar la base lista para usarse.

`create_all()` crea las tablas que falten, pero no toca las que ya existen. Lo
que se añadió después a una tabla ya creada se agrega aquí a mano, columna a
columna, para que la base de quien ya venía usando la app no se quede atrás.

Todo es idempotente: ejecutarlo sobre una base al día no cambia nada.
"""

from sqlalchemy import inspect, text

# Importar los modelos es lo que los registra en Base.metadata. Sin esta línea
# create_all() no sabría que hay tablas que crear.
from neon_storage import models  # noqa: F401
from neon_storage.database import Base, engine


def create_tables() -> None:
    """Create all SQLAlchemy model tables."""
    Base.metadata.create_all(bind=engine)


def ensure_user_role_column() -> None:
    """Agrega las columnas necesarias a la tabla Usuario si aún no existen."""
    inspector = inspect(engine)
    if "Usuario" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("Usuario")}

    if "rol" not in columns:
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE "Usuario" ADD COLUMN "rol" VARCHAR(20) DEFAULT \'estudiante\''))

    if "foto_path" not in columns:
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE "Usuario" ADD COLUMN "foto_path" VARCHAR(500) NULL'))


def ensure_quiz_answer_columns() -> None:
    """Agrega a QuizAnswer las columnas nuevas si la tabla ya existia.

    create_all() crea tablas, pero no toca las que ya estan. Sin esto, medir
    el tiempo de respuesta fallaria en cualquier base donde la tabla se creo
    antes de anadir la columna: justo la de quien ya venia usando la app.
    """
    inspector = inspect(engine)
    if "QuizAnswer" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("QuizAnswer")}

    if "elapsed_ms" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text('ALTER TABLE "QuizAnswer" ADD COLUMN "elapsed_ms" INTEGER NULL')
            )


def prepare_database() -> None:
    """Preparar la base al arrancar, pero sin que un fallo tumbe el servicio.

    Neon se duerme cuando lleva un rato sin uso. Si justo esta dormida cuando el
    servidor arranca, esto tardaria o fallaria, y sin proteccion el despliegue
    entero se daria por fallido aunque la aplicacion este perfecta. Se registra
    el problema y se sigue: la primera peticion de verdad reabrira la conexion.
    """
    try:
        create_tables()
        ensure_user_role_column()
        ensure_quiz_answer_columns()
    except Exception as exc:  # pragma: no cover - depende del entorno
        print(f"[arranque] No se pudo preparar la base de datos: {exc}")
        print("[arranque] El servicio arranca igualmente; se reintentara al usarla.")
