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
from neon_storage.database import Base, SessionLocal, engine


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


# Tablas que pasan a ser de un curso, con la restricción única que tenían y la
# que la sustituye ahora que el curso forma parte de la clave.
COURSE_SCOPED_TABLES = ("CourseOverride", "QuizAnswer", "ActivityCompletion", "ContentReview")
COURSE_UNIQUES = {
    "CourseOverride": (
        "uq_course_override",
        "uq_course_override_course",
        '"course_id", "scope", "target_id"',
    ),
    "ActivityCompletion": (
        "uq_activity_completion",
        "uq_activity_completion_course",
        '"usuario_id", "course_id", "section_id", "activity"',
    ),
    "ContentReview": (
        "uq_content_review_section",
        "uq_content_review_course_section",
        '"course_id", "section_id"',
    ),
}


def ensure_courses() -> None:
    """Pasa la base de «un curso para todos» a «un curso por docente».

    1. Añade `course_id` a las ediciones, las respuestas, las actividades
       terminadas y las revisiones.
    2. Crea el Curso general si no existe.
    3. Lo que no tenga curso pasa al Curso general. Es lo de antes de este
       cambio, y también lo que siga escribiendo el monolito mientras conviva
       con el gateway: se vuelve a repartir en cada arranque.
    4. Cambia las restricciones únicas para que incluyan el curso. Solo en
       PostgreSQL: SQLite no deja cambiarlas, y sus tablas de prueba ya nacen
       con las nuevas.
    """
    from neon_storage.courses import general_course
    from sqlalchemy import Table, MetaData, update

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    for table in COURSE_SCOPED_TABLES:
        if table not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        with engine.begin() as connection:
            if "course_id" not in columns:
                connection.execute(
                    text(
                        f'ALTER TABLE "{table}" ADD COLUMN "course_id" INTEGER NULL '
                        'REFERENCES "Course"(id)'
                    )
                )
            connection.execute(
                text(
                    f'CREATE INDEX IF NOT EXISTS "ix_{table}_course_id" '
                    f'ON "{table}" ("course_id")'
                )
            )

    db = SessionLocal()
    try:
        general_id = general_course(db).id
    finally:
        db.close()

    # Inicializas MetaData fuera o dentro del bloque según la estructura de tu función
    metadata = MetaData()

    with engine.begin() as connection:
        for table_name in COURSE_SCOPED_TABLES:
            if table_name in tables:
                # Reflejamos la estructura de la tabla de forma segura
                table = Table(table_name, metadata, autoload_with=connection)
                
                # Construimos la consulta UPDATE usando el constructor de SQLAlchemy
                stmt = (
                    update(table)
                    .where(table.c.course_id.is_(None))
                    .values(course_id=general_id)
                )
                
                connection.execute(stmt)

    if engine.dialect.name != "postgresql":
        return

    for table, (old, new, columns) in COURSE_UNIQUES.items():
        if table not in tables:
            continue
        existing = {u["name"] for u in inspect(engine).get_unique_constraints(table)}
        with engine.begin() as connection:
            if old in existing:
                connection.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{old}"'))
            if new not in existing:
                connection.execute(
                    text(f'ALTER TABLE "{table}" ADD CONSTRAINT "{new}" UNIQUE ({columns})')
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
        ensure_courses()
    except Exception as exc:  # pragma: no cover - depende del entorno
        print(f"[arranque] No se pudo preparar la base de datos: {exc}")
        print("[arranque] El servicio arranca igualmente; se reintentara al usarla.")
