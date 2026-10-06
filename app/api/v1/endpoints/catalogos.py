from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.organizacion import AreaCreate, AreaRead, EmpresaCreate, EmpresaRead
from app.services import organizacion_service

router = APIRouter(tags=["Catálogos organizacionales"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("/empresas", response_model=EmpresaRead, status_code=status.HTTP_201_CREATED)
async def crear_empresa(data: EmpresaCreate, db: DbSession):
    return await organizacion_service.crear_empresa(db, data)


@router.get("/empresas", response_model=list[EmpresaRead])
async def listar_empresas(db: DbSession):
    return await organizacion_service.listar_empresas(db)


@router.post("/areas", response_model=AreaRead, status_code=status.HTTP_201_CREATED)
async def crear_area(data: AreaCreate, db: DbSession):
    return await organizacion_service.crear_area(db, data)


@router.get("/areas", response_model=list[AreaRead])
async def listar_areas(db: DbSession, id_empresa: int | None = None):
    return await organizacion_service.listar_areas(db, id_empresa)
