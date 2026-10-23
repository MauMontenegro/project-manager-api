from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import BusinessRuleError
from app.core.security import CurrentActor
from app.schemas.configuracion import ConfiguracionGuardada, ConfiguracionLaboralIn, ConfiguracionLaboralRead, HorasLaborales
from app.services import configuracion_service

router = APIRouter(prefix="/configuracion", tags=["Configuración"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=ConfiguracionLaboralRead)
async def obtener_configuracion(db: DbSession):
    config = await configuracion_service.obtener(db)
    await db.commit()
    return config


@router.put("", response_model=ConfiguracionGuardada)
async def guardar_configuracion(data: ConfiguracionLaboralIn, db: DbSession, actor: CurrentActor):
    """Solo Administrador. Recalcula el presupuesto de los proyectos abiertos en modo automático."""
    return await configuracion_service.guardar(db, actor, data)


@router.get("/horas-laborales", response_model=HorasLaborales)
async def horas_laborales(desde: date, hasta: date, db: DbSession):
    """Horas laborales entre dos fechas (ambas incluidas) según el calendario vigente."""
    if hasta < desde:
        raise BusinessRuleError("hasta no puede ser anterior a desde")
    if (hasta - desde).days > 3660:
        raise BusinessRuleError("El rango no puede exceder 10 años")
    horas, dias = configuracion_service.horas_laborales(await configuracion_service.obtener(db), desde, hasta)
    return HorasLaborales(desde=desde, hasta=hasta, horas=horas, dias_laborables=dias)
