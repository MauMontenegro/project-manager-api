from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActor
from app.models.enums import EstadoTarea
from app.schemas.tarea import LineaBaseIn, ReprogramacionRead, TareaCreate, TareaRead, TareaUpdate
from app.services import tarea_service, visibilidad

router = APIRouter(tags=["Tareas"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/proyectos/{id_proyecto}/tareas", response_model=list[TareaRead])
async def listar_tareas_proyecto(
    id_proyecto: int, db: DbSession, actor: CurrentActor, id_etapa: int | None = None, id_usuario: int | None = None,
    estado: EstadoTarea | None = None,
):
    """Tareas del proyecto; en un conjunto, también las de todos sus subproyectos (vista general)."""
    await visibilidad.exigir_proyecto(db, actor, id_proyecto)
    return await tarea_service.listar_tareas_proyecto(
        db, id_proyecto, id_etapa=id_etapa, id_usuario=id_usuario, estado=estado
    )


@router.post("/proyectos/{id_proyecto}/tareas", response_model=TareaRead, status_code=status.HTTP_201_CREATED)
async def crear_tarea(id_proyecto: int, data: TareaCreate, db: DbSession, actor: CurrentActor):
    """Crea una tarea para una persona del proyecto. Solo el líder, el Gerente de su departamento o el Administrador.
    En un conjunto es una tarea propia, sin etapa, que no cuenta en el avance."""
    return await tarea_service.crear_tarea(db, actor, id_proyecto, data)


@router.get("/tareas", response_model=list[TareaRead])
async def listar_tareas_persona(
    db: DbSession, actor: CurrentActor, id_usuario: int | None = None, estado: EstadoTarea | None = None,
):
    """Todas las tareas de una persona: de sus proyectos y de sus tareas recurrentes (por defecto, las de quien consulta)."""
    return await tarea_service.listar_tareas_persona(db, actor, id_usuario=id_usuario, estado=estado)


@router.get("/tareas/{id_tarea}", response_model=TareaRead)
async def obtener_tarea(id_tarea: int, db: DbSession, actor: CurrentActor):
    return await tarea_service.obtener_tarea(db, actor, id_tarea)


@router.patch("/tareas/{id_tarea}", response_model=TareaRead)
async def actualizar_tarea(id_tarea: int, data: TareaUpdate, db: DbSession, actor: CurrentActor):
    """Edita o mueve la tarea en el kanban. Pasarla a `Finalizado` recalcula el avance del proyecto. Cambiar sus
    fechas queda como reprogramación; retrasar la fecha límite exige `motivo_cambio`."""
    return await tarea_service.actualizar_tarea(db, actor, id_tarea, data)


@router.delete("/tareas/{id_tarea}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_tarea(id_tarea: int, db: DbSession, actor: CurrentActor):
    await tarea_service.eliminar_tarea(db, actor, id_tarea)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tareas/{id_tarea}/reprogramaciones", response_model=list[ReprogramacionRead])
async def listar_reprogramaciones(id_tarea: int, db: DbSession, actor: CurrentActor):
    """Cambios de fechas de la tarea y nuevas líneas base, del más reciente al más antiguo."""
    await visibilidad.exigir_tarea(db, actor, id_tarea)
    return await tarea_service.reprogramaciones(db, id_tarea)


@router.post("/tareas/{id_tarea}/linea-base", response_model=TareaRead)
async def nueva_linea_base(id_tarea: int, data: LineaBaseIn, db: DbSession, actor: CurrentActor):
    """Fija las fechas vigentes como plan original (quien gestiona el proyecto). El desfase se mide desde ahí."""
    return await tarea_service.nueva_linea_base(db, actor, id_tarea, data)
