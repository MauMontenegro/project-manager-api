from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.enums import CausaRaiz, ResponsableOrigen
from app.schemas.bloqueo import BloqueoCerrar, BloqueoCreate, BloqueoRead, BloqueoUpdate
from app.services import bloqueo_service

router = APIRouter(prefix="/bloqueos", tags=["Bloqueos e interrupciones"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=BloqueoRead, status_code=status.HTTP_201_CREATED)
async def registrar_bloqueo(data: BloqueoCreate, db: DbSession):
    """Registra un bloqueo. Con `fecha_fin_bloqueo` informada se calcula `dias_impacto`; sin ella queda abierto."""
    return await bloqueo_service.registrar_bloqueo(db, data)


@router.get("", response_model=list[BloqueoRead])
async def listar_bloqueos(
    db: DbSession,
    id_proyecto: int | None = None,
    id_etapa: int | None = None,
    causa_raiz: CausaRaiz | None = None,
    responsable_origen: ResponsableOrigen | None = None,
    abierto: Annotated[bool | None, Query(description="true: sin fecha de fin; false: ya cerrados")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await bloqueo_service.listar_bloqueos(
        db,
        id_proyecto=id_proyecto,
        id_etapa=id_etapa,
        causa_raiz=causa_raiz,
        responsable_origen=responsable_origen,
        abierto=abierto,
        limit=limit,
        offset=offset,
    )


@router.get("/{id_bloqueo}", response_model=BloqueoRead)
async def obtener_bloqueo(id_bloqueo: int, db: DbSession):
    return await bloqueo_service.obtener_bloqueo(db, id_bloqueo)


@router.patch("/{id_bloqueo}", response_model=BloqueoRead)
async def actualizar_bloqueo(id_bloqueo: int, data: BloqueoUpdate, db: DbSession):
    """Actualiza datos del bloqueo; si tiene fecha de fin, recalcula `dias_impacto`."""
    return await bloqueo_service.actualizar_bloqueo(db, id_bloqueo, data)


@router.post("/{id_bloqueo}/cerrar", response_model=BloqueoRead)
async def cerrar_bloqueo(id_bloqueo: int, db: DbSession, data: BloqueoCerrar | None = None):
    """Libera el bloqueo (fecha de fin = ahora si no se indica) y calcula `dias_impacto`."""
    return await bloqueo_service.cerrar_bloqueo(db, id_bloqueo, data or BloqueoCerrar())


@router.delete("/{id_bloqueo}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_bloqueo(id_bloqueo: int, db: DbSession):
    await bloqueo_service.eliminar_bloqueo(db, id_bloqueo)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
