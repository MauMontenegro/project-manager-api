from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.enums import PerfilTecnico
from app.schemas.usuario import UsuarioCreate, UsuarioRead, UsuarioUpdate
from app.services import organizacion_service

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
async def crear_usuario(data: UsuarioCreate, db: DbSession):
    return await organizacion_service.crear_usuario(db, data)


@router.get("", response_model=list[UsuarioRead])
async def listar_usuarios(
    db: DbSession,
    id_area: int | None = None,
    perfil_tecnico: PerfilTecnico | None = None,
    activo: bool | None = None,
    q: Annotated[str | None, Query(description="Búsqueda por nombre o correo")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await organizacion_service.listar_usuarios(
        db, id_area=id_area, perfil_tecnico=perfil_tecnico, activo=activo, busqueda=q, limit=limit, offset=offset
    )


@router.get("/{id_usuario}", response_model=UsuarioRead)
async def obtener_usuario(id_usuario: int, db: DbSession):
    return await organizacion_service.obtener_usuario(db, id_usuario)


@router.patch("/{id_usuario}", response_model=UsuarioRead)
async def actualizar_usuario(id_usuario: int, data: UsuarioUpdate, db: DbSession):
    return await organizacion_service.actualizar_usuario(db, id_usuario, data)


@router.delete("/{id_usuario}", status_code=status.HTTP_204_NO_CONTENT)
async def desactivar_usuario(id_usuario: int, db: DbSession):
    """Baja lógica (`activo = false`); el registro se conserva por sus referencias históricas."""
    await organizacion_service.desactivar_usuario(db, id_usuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
