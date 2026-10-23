from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActor
from app.schemas.auth import CambiarPasswordIn, LoginIn, SesionToken
from app.services import auth_service

DbSession = Annotated[AsyncSession, Depends(get_db)]

# Público: es la puerta de entrada (no exige sesión).
publico = APIRouter(prefix="/auth", tags=["Autenticación"])
router = APIRouter(prefix="/auth", tags=["Autenticación"])


@publico.post("/login", response_model=SesionToken)
async def login(data: LoginIn, db: DbSession):
    """Correo y contraseña → sesión (`Authorization: Bearer …`). `401` si no coinciden; `429` tras 5 intentos
    fallidos en 15 minutos."""
    return await auth_service.login(db, data.correo, data.password)


@router.post("/password", response_model=SesionToken)
async def cambiar_password(data: CambiarPasswordIn, db: DbSession, actor: CurrentActor):
    """Cambia la contraseña propia (también la temporal). Devuelve una sesión nueva; las demás se cierran."""
    return await auth_service.cambiar_password(db, actor, data.actual, data.nueva)
