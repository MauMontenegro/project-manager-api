from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActor
from app.schemas.colaboracion import ComentarioCreate, EventoTarea, Involucrado, Notificaciones
from app.services import colaboracion_service, visibilidad

router = APIRouter(tags=["Colaboración"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/tareas/{id_tarea}/involucrados", response_model=list[Involucrado])
async def involucrados_de_tarea(id_tarea: int, db: DbSession, actor: CurrentActor):
    """Quiénes pueden comentar y ser mencionados en la tarea (de proyecto o recurrente)."""
    await visibilidad.exigir_tarea(db, actor, id_tarea)
    return await colaboracion_service.involucrados_de_tarea(db, id_tarea)


@router.get("/proyectos/{id_proyecto}/involucrados", response_model=list[Involucrado])
async def involucrados(id_proyecto: int, db: DbSession, actor: CurrentActor):
    """Personas activas del proyecto (líder y asignados): las que se pueden mencionar con @."""
    await visibilidad.exigir_proyecto(db, actor, id_proyecto)
    return await colaboracion_service.involucrados(db, id_proyecto)


@router.get("/tareas/{id_tarea}/actividad", response_model=list[EventoTarea])
async def actividad(id_tarea: int, db: DbSession, actor: CurrentActor):
    """Línea de tiempo de la tarea: cada cambio (quién, cuándo, qué) y cada comentario."""
    await visibilidad.exigir_tarea(db, actor, id_tarea)
    return await colaboracion_service.actividad(db, id_tarea)


@router.post("/tareas/{id_tarea}/comentarios", response_model=EventoTarea, status_code=status.HTTP_201_CREATED)
async def comentar(id_tarea: int, data: ComentarioCreate, db: DbSession, actor: CurrentActor):
    """Comenta la tarea. Cada persona en `menciones` recibe una notificación."""
    await visibilidad.exigir_tarea(db, actor, id_tarea)
    return await colaboracion_service.comentar(db, actor, id_tarea, data)


@router.delete("/comentarios/{id_comentario}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_comentario(id_comentario: int, db: DbSession, actor: CurrentActor):
    await colaboracion_service.eliminar_comentario(db, actor, id_comentario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/notificaciones", response_model=Notificaciones)
async def notificaciones(
    db: DbSession, actor: CurrentActor, solo_no_leidas: bool = False, limit: Annotated[int, Query(ge=1, le=100)] = 30,
):
    """Menciones de quien consulta, de la más reciente a la más antigua, y cuántas no ha leído."""
    return await colaboracion_service.notificaciones(db, actor, solo_no_leidas=solo_no_leidas, limit=limit)


@router.post("/notificaciones/leer-todas", status_code=status.HTTP_204_NO_CONTENT)
async def leer_todas(db: DbSession, actor: CurrentActor):
    await colaboracion_service.marcar_leidas(db, actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notificaciones/{id_mencion}/leer", status_code=status.HTTP_204_NO_CONTENT)
async def leer(id_mencion: int, db: DbSession, actor: CurrentActor):
    await colaboracion_service.marcar_leidas(db, actor, id_mencion)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
