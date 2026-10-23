from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActor
from app.schemas.equipo_trabajo import EquipoTrabajoIn, EquipoTrabajoRead, EquipoTrabajoUpdate
from app.services import equipo_trabajo_service

router = APIRouter(prefix="/equipos-trabajo", tags=["Equipos de trabajo"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[EquipoTrabajoRead])
async def listar(db: DbSession, id_usuario: Annotated[int | None, Query(description="Solo los equipos de esa persona")] = None):
    """Equipos de trabajo con sus personas y conteos de proyectos y bloqueos abiertos."""
    return await equipo_trabajo_service.listar(db, id_usuario=id_usuario)


@router.post("", response_model=EquipoTrabajoRead, status_code=status.HTTP_201_CREATED)
async def crear(data: EquipoTrabajoIn, db: DbSession, actor: CurrentActor):
    """Gerentes o Administrador."""
    return await equipo_trabajo_service.crear(db, actor, data)


@router.get("/{id_equipo_trabajo}", response_model=EquipoTrabajoRead)
async def obtener(id_equipo_trabajo: int, db: DbSession):
    return await equipo_trabajo_service.obtener(db, id_equipo_trabajo)


@router.patch("/{id_equipo_trabajo}", response_model=EquipoTrabajoRead)
async def actualizar(id_equipo_trabajo: int, data: EquipoTrabajoUpdate, db: DbSession, actor: CurrentActor):
    """Gerentes o Administrador. `miembros` reemplaza la lista completa."""
    return await equipo_trabajo_service.actualizar(db, actor, id_equipo_trabajo, data)


@router.delete("/{id_equipo_trabajo}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(id_equipo_trabajo: int, db: DbSession, actor: CurrentActor):
    """Sus proyectos quedan sin equipo de trabajo. Gerentes o Administrador."""
    await equipo_trabajo_service.eliminar(db, actor, id_equipo_trabajo)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
