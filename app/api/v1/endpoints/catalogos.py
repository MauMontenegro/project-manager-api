from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActor
from app.schemas.organizacion import (
    AreaCreate, AreaRead, EliminarEmpresasIn, EmpresaCreate, EmpresaRead, EmpresasEliminadas,
)
from app.services import organizacion_service

router = APIRouter(tags=["Catálogos organizacionales"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("/empresas", response_model=EmpresaRead, status_code=status.HTTP_201_CREATED)
async def crear_empresa(data: EmpresaCreate, db: DbSession):
    return await organizacion_service.crear_empresa(db, data)


@router.get("/empresas", response_model=list[EmpresaRead])
async def listar_empresas(db: DbSession):
    return await organizacion_service.listar_empresas(db)


@router.post("/empresas/eliminar", response_model=EmpresasEliminadas)
async def eliminar_empresas(data: EliminarEmpresasIn, db: DbSession, actor: CurrentActor):
    """Elimina varias empresas a la vez (con sus áreas). Las que están en uso no se eliminan y se reportan
    con su motivo. Solo el Administrador."""
    return await organizacion_service.eliminar_empresas(db, actor, data.ids)


@router.delete("/empresas/{id_empresa}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_empresa(id_empresa: int, db: DbSession, actor: CurrentActor):
    """`409` si está en uso (proyectos, demanda o compromisos). Solo el Administrador."""
    await organizacion_service.eliminar_empresa(db, actor, id_empresa)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/areas", response_model=AreaRead, status_code=status.HTTP_201_CREATED)
async def crear_area(data: AreaCreate, db: DbSession):
    return await organizacion_service.crear_area(db, data)


@router.get("/areas", response_model=list[AreaRead])
async def listar_areas(db: DbSession, id_empresa: int | None = None):
    return await organizacion_service.listar_areas(db, id_empresa)

