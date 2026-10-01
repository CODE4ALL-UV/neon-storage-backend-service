"""La conexión con Neon.

Es el único sitio del backend que sabe hablar con la base de datos. Todos los
microservicios que guardan algo importan de aquí el motor, la sesión y la base
de los modelos: hay una sola cadena de conexión que configurar y un solo lugar
donde arreglarla si falla.
"""

import os
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# Carga obligatoria de las variables del archivo .env
load_dotenv()


def _clean_database_url(raw: str | None) -> str:
    """Deja la cadena de conexion utilizable, o explica que le falta.

    Al copiarla de un archivo .env es facil arrastrar las comillas, y entonces
    SQLAlchemy falla con «Could not parse SQLAlchemy URL», que no dice a nadie
    que el problema son dos comillas. Aqui se quitan y, si aun asi no sirve, se
    dice en castellano que esta mal.
    """
    if raw is None:
        raise ValueError(
            "Falta la variable DATABASE_URL. En Render se escribe en "
            "Environment; en local, en el archivo .env."
        )

    url = raw.strip()

    # Comillas arrastradas al copiar la linea entera del .env.
    for quote in ('"', "'"):
        if len(url) >= 2 and url.startswith(quote) and url.endswith(quote):
            url = url[1:-1].strip()

    if not url:
        raise ValueError(
            "La variable DATABASE_URL esta vacia. Copia la cadena de "
            "conexion de Neon, sin comillas."
        )

    # Los paneles muestran la cadena partida en varias lineas para que quepa.
    # Al copiarla se cuelan saltos de linea y espacios que no forman parte de
    # ella: una URL de conexion nunca lleva espacios en blanco.
    url = "".join(url.split())

    # Algunos paneles dan la forma antigua; SQLAlchemy quiere postgresql://.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    if "://" not in url:
        # El caso mas comun: se copio solo el final, desde el signo de
        # interrogacion. Decirlo ahorra buscar a ciegas.
        if url.startswith("?") or url.startswith("sslmode="):
            raise ValueError(
                "DATABASE_URL solo trae la parte final de la cadena "
                f"({url[:30]}...). Falta todo lo de delante. Copiala entera, "
                "desde postgresql:// hasta el final, en una sola linea."
            )

        raise ValueError(
            "DATABASE_URL no parece una cadena de conexion: deberia empezar "
            f"por postgresql://. Llego esto: {url[:30]}..."
        )

    return url


DATABASE_URL = _clean_database_url(os.getenv("DATABASE_URL"))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Provide a transactional database session for FastAPI dependencies."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
