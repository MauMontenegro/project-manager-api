from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.enums import EstadoProyecto, Semaforo
from app.schemas.proyecto import (
    AsignacionCreate,
    AsignacionRead,
    EtapaCreate,
    EtapaRead,
    PortafolioPage,
    ProyectoCambioEstado,
    ProyectoCreate,
    ProyectoDetalle,
    ProyectoUpdate,
)
from app.services import proyecto_service

router = APIRouter(prefix="/proyectos", tags=["Proyectos"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=ProyectoDetalle, status_code=status.HTTP_201_CREATED)
async def crear_proyecto(data: ProyectoCreate, db: DbSession):
    """Crea un proyecto en estado 'Iniciación'. Si proviene de una solicitud de demanda, esta pasa a 'En Ejecución'."""
    return await proyecto_service.crear_proyecto(db, data)


@router.get("", response_model=PortafolioPage)
async def consultar_portafolio(
    db: DbSession,
    semaforo: Semaforo | None = None,
    id_empresa: Annotated[int | None, Query(description="Empresa impactada o solicitante")] = None,
    estado: EstadoProyecto | None = None,
    lider_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Portafolio de proyectos con filtros por semáforo, empresa, estado y líder."""
    items, total = await proyecto_service.listar_portafolio(
        db, semaforo=semaforo, id_empresa=id_empresa, estado=estado, lider_id=lider_id, limit=limit, offset=offset
    )
    return PortafolioPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{id_proyecto}", response_model=ProyectoDetalle)
async def obtener_proyecto(id_proyecto: int, db: DbSession):
    return await proyecto_service.obtener_proyecto(db, id_proyecto)


@router.patch("/{id_proyecto}", response_model=ProyectoDetalle)
async def actualizar_proyecto(id_proyecto: int, data: ProyectoUpdate, db: DbSession):
    return await proyecto_service.actualizar_proyecto(db, id_proyecto, data)


@router.patch("/{id_proyecto}/estado", response_model=ProyectoDetalle)
async def cambiar_estado(id_proyecto: int, data: ProyectoCambioEstado, db: DbSession):
    """Avanza el ciclo de vida validando las transiciones permitidas."""
    return await proyecto_service.cambiar_estado(db, id_proyecto, data)


@router.post("/{id_proyecto}/etapas", response_model=EtapaRead, status_code=status.HTTP_201_CREATED)
async def crear_etapa(id_proyecto: int, data: EtapaCreate, db: DbSession):
    return await proyecto_service.crear_etapa(db, id_proyecto, data)


@router.get("/{id_proyecto}/etapas", response_model=list[EtapaRead])
async def listar_etapas(id_proyecto: int, db: DbSession):
    return await proyecto_service.listar_etapas(db, id_proyecto)


@router.post("/{id_proyecto}/asignaciones", response_model=AsignacionRead, status_code=status.HTTP_201_CREATED)
async def asignar_recurso(id_proyecto: int, data: AsignacionCreate, db: DbSession):
    """Asigna un usuario activo a una etapa del proyecto."""
    return await proyecto_service.asignar_recurso(db, id_proyecto, data)


@router.get("/{id_proyecto}/asignaciones", response_model=list[AsignacionRead])
async def listar_asignaciones(id_proyecto: int, db: DbSession):
    return await proyecto_service.listar_asignaciones(db, id_proyecto)
