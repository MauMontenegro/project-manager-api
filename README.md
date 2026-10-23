# Petroil Project Manager API

Backend FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL para la Plataforma Inteligente de Gestión de Proyectos.
Esquema según [arquitectura-base-datos-petroil.md](arquitectura-base-datos-petroil.md) y [Specifications.md](Specifications.md).

## Ejecución

```bash
docker compose up --build
```

La API aplica las migraciones (`alembic upgrade head`) al arrancar. Docs interactivas: http://localhost:8000/docs

## Desarrollo local

Requiere Python 3.12 (las versiones fijadas de `pydantic-core` aún no compilan en 3.14).

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

## Endpoints (`/api/v1`)

| Recurso | Rutas |
| :--- | :--- |
| Catálogos | `POST/GET /empresas`, `POST/GET /areas` |
| Usuarios | `POST/GET /usuarios`, `GET/PATCH/DELETE /usuarios/{id}` (DELETE = baja lógica) |
| Proyectos | `POST /proyectos`, `GET /proyectos` (portafolio: `semaforo`, `id_empresa`, `estado`, `lider_id`), `GET/PATCH/DELETE /proyectos/{id}` (DELETE = borrado definitivo, solo Director), `PATCH /proyectos/{id}/estado` |
| Etapas y recursos | `GET /proyectos/{id}/etapas`, `PATCH /proyectos/{id}/etapas/{id_etapa}`, `POST/GET /proyectos/{id}/asignaciones` |
| Tareas | `POST/GET /proyectos/{id}/tareas`, `GET /tareas` (las de una persona), `PATCH/DELETE /tareas/{id}` |
| Colaboración | `GET /tareas/{id}/actividad`, `POST /tareas/{id}/comentarios`, `DELETE /comentarios/{id}`, `GET /proyectos/{id}/involucrados`, `GET /notificaciones`, `POST /notificaciones/{id}/leer`, `POST /notificaciones/leer-todas` |
| Configuración | `GET/PUT /configuracion` (calendario laboral, PUT solo Director), `GET /configuracion/horas-laborales` |
| Bloqueos | `POST/GET /bloqueos`, `GET/PATCH/DELETE /bloqueos/{id}`, `POST /bloqueos/{id}/cerrar` |

## Reglas de negocio implementadas

- Ciclo de vida en 5 macro-etapas (Análisis y Viabilidad → Despliegue y Cierre) de 20 % cada una, con sus estatus permitidos; ver API.md §5.1. Las 5 etapas se crean con el proyecto.
- El avance se calcula con las tareas finalizadas de cada etapa; al terminar las de la etapa actual el proyecto avanza solo.
- Al crear un proyecto desde una solicitud, esta pasa a `En Ejecución` (una solicitud solo admite un proyecto).
- `dias_impacto` de un bloqueo = (fin − inicio) en días, 2 decimales; se recalcula al cerrar o editar.
- Una asignación valida que la etapa pertenezca al proyecto, que el usuario esté activo y que no esté duplicada.
