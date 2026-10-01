# neon-storage-backend-service
Persistencia de Code4All en Neon (PostgreSQL).

Es el recuadro «Base de datos / Persistencia» del diagrama. No es un servicio
con rutas propias: es la capa de datos que comparten los microservicios. Es el
único sitio que sabe hablar con Neon, así que hay una sola cadena de conexión
que configurar y un solo lugar donde arreglarla.

Antes este repositorio iba a ser la conexión con Firebase Cloud Storage. El
proyecto guarda sus datos en Neon, así que pasó a ser eso.

## Qué tiene

| Módulo | Para qué |
|---|---|
| `neon_storage/database.py` | La conexión: limpia la `DATABASE_URL` (comillas, saltos de línea, `postgres://`), crea el motor y da `get_db` para FastAPI. |
| `neon_storage/models.py` | Todas las tablas. |
| `neon_storage/schema.py` | `prepare_database()`: crea las tablas que falten y añade las columnas nuevas a las que ya existían. No tumba el arranque si Neon está dormida. |

```python
from neon_storage import get_db, prepare_database
from neon_storage.models import Usuario, CourseOverride
```

## Qué servicio es dueño de cada tabla

Hay una sola base, pero cada tabla la **escribe** un solo servicio. Los demás
pueden leerla para sus informes.

| Tabla | La escribe | La leen también |
|---|---|---|
| `Usuario`, `TipoDiscapacidad` | user-management | assessment, progress-tracking |
| `CourseOverride` | course-content | progress-tracking |
| `QuizAnswer`, `ActivityCompletion` | assessment | — |
| `student_performance`, `TeacherReview`, `ContentReview` | progress-tracking | — |

Una tabla nueva o una columna nueva se añade aquí, en `models.py`. Si la tabla
ya existe en Neon, `create_all()` no la toca: la columna se agrega a mano en
`schema.py`, como `ensure_quiz_answer_columns()`.

## Configuración

`DATABASE_URL` con la cadena de Neon, en una sola línea y sin comillas. La del
pooler (el host lleva `-pooler`) aguanta muchas más conexiones si algún día
los servicios se despliegan por separado.

## Pruebas

```powershell
pip install -r requirements.txt
pytest tests
```
