from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActor
from app.models.enums import CausaRaiz, DepartamentoProyecto, ResponsableOrigen
from app.schemas.bloqueo import BloqueoCerrar, BloqueoCreate, BloqueoRead, BloqueoUpdate, ResumenBloqueos
from app.services import bloqueo_service

router = APIRouter(prefix="/bloqueos", tags=["Bloqueos e interrupciones"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=BloqueoRead, status_code=status.HTTP_201_CREATED)
async def registrar_bloqueo(data: BloqueoCreate, db: DbSession, actor: CurrentActor):
    """Reporta un bloqueo de una tarea (la persona asignada o quien gestiona el proyecto) o de una etapa (quien
    gestiona). Sin `fecha_fin_bloqueo` queda abierto."""
    return await bloqueo_service.registrar_bloqueo(db, actor, data)


@router.get("", response_model=list[BloqueoRead])
async def listar_bloqueos(
    db: DbSession,
    actor: CurrentActor,
    id_proyecto: Annotated[int | None, Query(description="Un conjunto incluye los de sus subproyectos")] = None,
    departamento: DepartamentoProyecto | None = None,
    id_equipo_trabajo: int | None = None,
    id_etapa: int | None = None,
    id_tarea: int | None = None,
    causa_raiz: CausaRaiz | None = None,
    responsable_origen: ResponsableOrigen | None = None,
    abierto: Annotated[bool | None, Query(description="true: sin fecha de fin; false: ya resueltos")] = None,
    automatico: Annotated[bool | None, Query(description="true: esperas por dependencias; false: reportados")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Abiertos primero, luego por inicio (más recientes primero). Los abiertos traen su duración hasta ahora."""
    return await bloqueo_service.listar_bloqueos(
        db, actor, id_proyecto=id_proyecto, departamento=departamento, id_equipo_trabajo=id_equipo_trabajo, id_etapa=id_etapa, id_tarea=id_tarea,
        causa_raiz=causa_raiz, responsable_origen=responsable_origen, abierto=abierto, automatico=automatico,
        limit=limit, offset=offset,
    )


@router.get("/resumen", response_model=ResumenBloqueos)
async def resumen_bloqueos(
    db: DbSession,
    actor: CurrentActor,
    id_proyecto: Annotated[int | None, Query(description="Un conjunto incluye sus subproyectos")] = None,
    departamento: DepartamentoProyecto | None = None,
    id_equipo_trabajo: int | None = None,
    desde: date | None = None,
    hasta: date | None = None,
):
    """Tiempo bloqueado (días y horas hábiles) por causa, origen y proyecto, y desfases de las tareas con su
    explicación (reprogramaciones por bloqueo, sin bloqueo y ejecución)."""
    return await bloqueo_service.resumen(
        db, actor, id_proyecto=id_proyecto, departamento=departamento, id_equipo_trabajo=id_equipo_trabajo, desde=desde, hasta=hasta,
    )


@router.get("/{id_bloqueo}", response_model=BloqueoRead)
async def obtener_bloqueo(id_bloqueo: int, db: DbSession, actor: CurrentActor):
    return await bloqueo_service.obtener_bloqueo(db, id_bloqueo, actor)


@router.patch("/{id_bloqueo}", response_model=BloqueoRead)
async def actualizar_bloqueo(id_bloqueo: int, data: BloqueoUpdate, db: DbSession, actor: CurrentActor):
    """Corrige los datos del bloqueo; con fecha de fin recalcula su duración. Los automáticos no se editan."""
    return await bloqueo_service.actualizar_bloqueo(db, actor, id_bloqueo, data)


@router.post("/{id_bloqueo}/cerrar", response_model=BloqueoRead)
async def cerrar_bloqueo(id_bloqueo: int, db: DbSession, actor: CurrentActor, data: BloqueoCerrar | None = None):
    """Resuelve el bloqueo (fin = ahora si no se indica) y mide su duración en días y horas hábiles."""
    return await bloqueo_service.cerrar_bloqueo(db, actor, id_bloqueo, data or BloqueoCerrar())


@router.delete("/{id_bloqueo}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_bloqueo(id_bloqueo: int, db: DbSession, actor: CurrentActor):
    """Solo para registros equivocados (quien gestiona el proyecto): un bloqueo real se resuelve."""
    await bloqueo_service.eliminar_bloqueo(db, actor, id_bloqueo)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
