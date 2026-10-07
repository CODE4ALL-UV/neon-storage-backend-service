# neon-storage-backend-service · Capa de datos compartida (Neon)

Este repositorio es la **capa de datos** de Code4All. No es un servicio con
rutas propias: es una librería de Python (`neon_storage`) que usan los demás
microservicios para hablar con la base de datos.

Todo Code4All guarda sus datos en **una sola base PostgreSQL en
[Neon](https://neon.tech)**. En vez de que cada servicio tenga su propia
conexión y sus propias copias de las tablas, todo eso vive aquí:

- **la conexión** con Neon, en un solo lugar: hay una sola cadena de conexión
  que configurar y un solo sitio donde arreglarla si algo falla;
- **la definición de todas las tablas**;
- **las migraciones** que ponen al día una base que ya existía;
- **lo común de los cursos** (el Curso general y los códigos de inscripción),
  para que cada servicio no lo resuelva a su manera.

En el diagrama de la arquitectura es el recuadro «Base de datos /
Persistencia».

## Cómo lo usan los demás servicios

```python
from neon_storage import get_db, prepare_database
from neon_storage.models import Usuario, CourseOverride
from neon_storage.courses import general_course
```

No se instala con `pip`. Los servicios lo encuentran porque está en el
`sys.path`:

- **En el gateway**, este repositorio es un submódulo en `services/` y el
  `main.py` del gateway añade cada servicio al `sys.path` al arrancar.
- **Corriendo un servicio solo**, se clona este repositorio al lado y se añade
  con `PYTHONPATH` (cada README explica cómo).
- **En las pruebas**, el `conftest.py` de cada servicio busca los repositorios
  hermanos `*-backend-service` y los añade solo.

| Servicio | Qué usa de aquí |
|---|---|
| Gateway | `prepare_database()` al arrancar. |
| user-management | `get_db`, `Usuario`, `TipoDiscapacidad`. |
| course-content | `get_db`, los modelos de cursos y ediciones, y todo `courses.py`. |
| assessment | `get_db`, `QuizAnswer`, `ActivityCompletion`, `CourseEnrollment`, `Usuario`. |
| progress-tracking | `get_db`, `general_course` y los modelos de revisiones, cursos y rendimiento. |
| device-management | Solo `engine`, para comprobar que la base responde. |
| accessibility, multimodal-interaction | Nada: no usan base de datos. |

## Qué hay en el paquete

```
neon_storage/
├── __init__.py    exporta Base, SessionLocal, engine, get_db y prepare_database
├── database.py    la conexión: limpia la DATABASE_URL, crea el motor y las sesiones
├── models.py      todas las tablas
├── schema.py      prepare_database(): crea lo que falte y migra lo que ya existía
└── courses.py     el Curso general y los códigos de inscripción
tests/
├── conftest.py
├── test_database_url.py
└── test_courses_migration.py
```

## La conexión (`database.py`)

Lee la variable `DATABASE_URL` (también desde un `.env`, con `python-dotenv`) y
la limpia antes de usarla, porque al copiarla del panel de Neon o de Render es
fácil que se cuele algo:

1. Le quita espacios y comillas (`"` o `'`) de los extremos.
2. Le quita los saltos de línea y espacios de en medio, por si se pegó partida
   en varias líneas.
3. Cambia `postgres://` por `postgresql://`.
4. Cambia `postgresql://` por **`postgresql+psycopg2://`**. SQLAlchemy 2.1
   busca por defecto el driver psycopg 3, y el que tenemos instalado es
   psycopg2. Si la cadena ya trae un driver, se respeta.
5. Si después de todo eso no parece una cadena de conexión, falla con un
   mensaje que explica qué pasó. Por ejemplo, si solo se pegó la parte final
   (`?sslmode=require`).

**Si falta `DATABASE_URL`, el import falla** y el servicio no arranca. No hay
una base de respaldo: SQLite solo se usa en las pruebas.

El motor se crea con `pool_pre_ping=True`, que revisa cada conexión antes de
usarla. Hace falta porque Neon se duerme cuando no se usa y cierra las
conexiones abiertas.

Para FastAPI se usa `get_db`, que abre una sesión por petición y la cierra al
terminar:

```python
@router.get("/algo")
def algo(db: Session = Depends(get_db)):
    ...
```

## Las tablas (`models.py`)

Hay una sola base, pero **cada tabla la escribe un solo servicio**. Los demás
pueden leerla, por ejemplo para sus informes.

| Tabla | Qué guarda | La escribe | La leen también |
|---|---|---|---|
| `Usuario` | Las cuentas: nombre, correo (único), contraseña cifrada con bcrypt, rol (`estudiante`, `docente` o `director`), tipo de discapacidad, foto y fecha de registro. | user-management | course-content, assessment, progress-tracking |
| `TipoDiscapacidad` | El catálogo de tipos de discapacidad (id y nombre). | Ningún servicio: no hay código que la llene | user-management |
| `Course` | Los cursos: título, descripción, docente, código de inscripción (único) y si es el Curso general. | course-content | assessment, progress-tracking |
| `CourseEnrollment` | Qué estudiante está en qué curso (un estudiante no se repite en el mismo curso). | course-content | assessment, progress-tracking |
| `CourseOverride` | Lo que un docente editó del temario: el contenido completo en JSON, de qué curso, qué sección o módulo, quién lo editó y cuándo. | course-content | progress-tracking |
| `QuizAnswer` | Una fila por pregunta respondida: estudiante, curso, sección, actividad, número de pregunta, enunciado, si acertó y cuánto tardó. | assessment | course-content |
| `ActivityCompletion` | Qué actividades terminó cada estudiante, una vez por curso, sección y actividad. | assessment | course-content |
| `TeacherReview` | Las valoraciones de la dirección a cada docente (nota de 1 a 5 y comentario), con su fecha. Se guarda el historial. | progress-tracking | — |
| `ContentReview` | La revisión de cada sección por curso: `aprobado` u `observado`, con comentario. Una por curso y sección. | progress-tracking | course-content (las borra al borrar un curso) |
| `student_performance` | El rendimiento por lección que venía del monolito: puntaje y contadores. | progress-tracking | — |

Algunas cosas que conviene saber:

- **No hay tablas de módulos ni de ejercicios.** El temario de fábrica vive en
  la app. Aquí solo se guarda lo que se editó (`CourseOverride`), y los
  nombres de los módulos van en esa misma tabla con `scope = 'module'`.
- Las tablas se relacionan con **claves foráneas** (casi todo apunta a
  `Usuario` o a `Course`), pero no se definen `relationship()` de SQLAlchemy:
  las consultas se hacen a mano en cada servicio y no hay borrados en cascada.
- En PostgreSQL los nombres de las tablas van con mayúscula y entre comillas
  (`"Usuario"`, `"Course"`), salvo `student_performance`.

## Cursos por docente y el Curso general (`courses.py`)

Cada docente tiene sus propios cursos y los estudiantes entran con un código.
Las ediciones, las respuestas, las actividades terminadas y las revisiones
llevan `course_id`.

- **Curso general:** no es de ningún docente (`teacher_id` vacío y
  `is_general = true`), se llama «Curso general de Code4All», lo ven todos los
  estudiantes sin inscribirse y solo lo edita la dirección. Ahí quedó todo lo
  que existía antes de que hubiera cursos por docente. `general_course(db)` lo
  devuelve y, si no existe, lo crea.
- **Códigos de inscripción:** `new_join_code(db)` genera uno de **6
  caracteres** al azar (con `secrets`) que no tenga otro curso. Usa solo
  `ABCDEFGHJKMNPQRSTUVWXYZ23456789`: sin `0`, `O`, `1`, `I` ni `L`, porque el
  código se dicta en clase y se copia de la pizarra.
- `normalize_join_code(code)` quita los espacios y pasa a mayúsculas lo que
  escribe el estudiante, así `k7m p3x` vale lo mismo que `K7MP3X`.
- `is_enrolled(db, course_id, student_id)` dice si un estudiante está inscrito.

Aquí no hay reglas de permisos: quién puede ver o editar un curso lo decide
[course-content](https://github.com/CODE4ALL-UV/course-content-backend-service).

## Las migraciones (`schema.py`)

No usamos Alembic. `prepare_database()` se llama al arrancar el gateway (y al
arrancar solos los servicios que tienen tablas) y pone la base al día. Todo es **idempotente**: se
puede correr las veces que sea y no repite nada.

1. **`create_tables()`** crea las tablas que no existan. No toca las que ya
   existen.
2. **`ensure_user_role_column()`** añade a `Usuario` las columnas `rol` (por
   defecto `estudiante`) y `foto_path` si una base vieja no las tiene.
3. **`ensure_quiz_answer_columns()`** añade `elapsed_ms` a `QuizAnswer`.
4. **`ensure_courses()`** hace el paso de «un curso para todos» a «un curso por
   docente»:
   - añade `course_id` (con su índice) a `CourseOverride`, `QuizAnswer`,
     `ActivityCompletion` y `ContentReview`;
   - crea el Curso general si no existe;
   - le asigna al Curso general todo lo que tenga `course_id` vacío. Lo hace
     **en cada arranque**, para recoger también lo que siga escribiendo el
     monolito mientras conviva con el gateway;
   - en PostgreSQL cambia las restricciones únicas para que incluyan el curso
     (por ejemplo, la misma sección editada puede existir una vez **por
     curso**). En SQLite este paso se salta, porque SQLite no deja cambiarlas y
     ahí las tablas ya nacen con las nuevas.

Si la base no responde al arrancar (por ejemplo, porque Neon está dormida),
`prepare_database()` escribe el error en el log y **deja arrancar el servicio
igual**; se vuelve a intentar cuando se use la base.

### Cómo añadir una tabla o una columna

- **Tabla nueva:** se define en `models.py`. `create_tables()` la crea sola en
  el siguiente arranque.
- **Columna nueva en una tabla que ya existe:** además de ponerla en
  `models.py`, hay que añadirla a mano en `schema.py`, con una función como
  `ensure_quiz_answer_columns()`. `create_all()` no modifica tablas que ya
  existen.

## Variables de entorno

| Variable | Para qué | ¿Obligatoria? |
|---|---|---|
| `DATABASE_URL` | La cadena de conexión de Neon, en una sola línea y sin comillas. Mejor la del *pooler* (el host lleva `-pooler`), que aguanta muchas más conexiones si algún día los servicios se despliegan por separado. | Sí |

Está en `.env.example`.

## Pruebas

```powershell
pip install -r requirements.txt
pytest tests
```

No tocan Neon: `conftest.py` fuerza una base SQLite temporal.

- `test_database_url.py` (7 pruebas): la limpieza de la cadena de conexión.
  Que quite comillas, que una una cadena partida en varias líneas, que pase
  `postgres://` a `postgresql+psycopg2://`, que respete un driver ya elegido y
  que los mensajes de error expliquen qué falta.
- `test_courses_migration.py` (4 pruebas): crea una base con el esquema de
  antes (sin cursos) y comprueba que, después de `prepare_database()`, todo
  queda en el Curso general sin filas huérfanas; que preparar dos veces no
  crea un segundo Curso general; y que los códigos de inscripción son únicos,
  de 6 caracteres, fáciles de dictar y se reconocen escritos en minúsculas o
  con espacios.

En GitHub, cada push o pull request a `main` corre las pruebas con cobertura y
la sube a Codacy (`.github/workflows/codacy-coverage.yml`).

## Un poco de historia

Al principio este repositorio iba a ser la conexión con Firebase Cloud
Storage. El proyecto terminó guardando sus datos en Neon, así que pasó a ser
esto. El código salió del monolito de user-management sin cambios y después se
le añadieron los cursos por docente.

## Los repositorios de Code4All

| Parte | Repositorio |
|---|---|
| App (Flutter) | [Front-end](https://github.com/CODE4ALL-UV/Front-end) |
| API Gateway | [Back-end](https://github.com/CODE4ALL-UV/Back-end) |
| Gestión de usuarios | [user-management-backend-service](https://github.com/CODE4ALL-UV/user-management-backend-service) |
| Curso y contenidos de Python | [course-content-backend-service](https://github.com/CODE4ALL-UV/course-content-backend-service) |
| Ejercicios y evaluación | [assessment-backend-service](https://github.com/CODE4ALL-UV/assessment-backend-service) |
| Progreso y seguimiento | [progress-tracking-backend-service](https://github.com/CODE4ALL-UV/progress-tracking-backend-service) |
| Accesibilidad y adaptación | [accessibility-backend-service](https://github.com/CODE4ALL-UV/accessibility-backend-service) |
| Interacción multimodal | [multimodal-interaction-backend-service](https://github.com/CODE4ALL-UV/multimodal-interaction-backend-service) |
| Infraestructura y dispositivos | [device-management-backend-service](https://github.com/CODE4ALL-UV/device-management-backend-service) |
| **Capa de datos compartida (Neon)** | **este repositorio** |
