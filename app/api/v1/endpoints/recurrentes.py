from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActor
from app.models.enums import Departamento, EstadoTarea, Frecuencia
from app.schemas.recurrente import TareaRecurrenteCreate, TareaRecurrenteRead, TareaRecurrenteUpdate
from app.schemas.tarea import TareaRead
from app.services import recurrente_service, tarea_service

router = APIRouter(prefix="/tareas-recurrentes", tags=["Tareas recurrentes"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
Etiquetas = Annotated[list[int] | None, Query(description="Con cualquiera de estas etiquetas")]


@router.get("/tareas", response_model=list[TareaRead])
async def panel_tareas(
    db: DbSession, actor: CurrentActor,
    id_usuario: int | None = None, departamento: Departamento | None = None, frecuencia: Frecuencia | None = None,
    etiquetas: Etiquetas = None, estado: EstadoTarea | None = None, id_recurrente: int | None = None,
    desde: Annotated[date | None, Query(description="Tareas cuyo fin es igual o posterior")] = None,
    hasta: Annotated[date | None, Query(description="Tareas cuyo inicio es igual o anterior")] = None,
    vencidas: Annotated[bool, Query(description="Solo las no finalizadas cuyo fin ya pasó")] = False,
):
    """Panel de operación: las tareas generadas por las tareas recurrentes visibles para quien consulta
    (las suyas; un Gerente, las de su departamento; el Administrador, todas). Máximo 500."""
    return await tarea_service.listar_tareas_recurrentes(
        db, actor, id_usuario=id_usuario, departamento=departamento.value if departamento else None,
        frecuencia=frecuencia, etiquetas=etiquetas, estado=estado, desde=desde, hasta=hasta, vencidas=vencidas,
        id_recurrente=id_recurrente,
    )


@router.get("", response_model=list[TareaRecurrenteRead])
async def listar(
    db: DbSession, actor: CurrentActor,
    id_usuario: int | None = None, departamento: Departamento | None = None, frecuencia: Frecuencia | None = None,
    activa: bool | None = None, etiquetas: Etiquetas = None,
):
    return await recurrente_service.listar(
        db, actor, id_usuario=id_usuario, departamento=departamento.value if departamento else None,
        frecuencia=frecuencia, activa=activa, etiquetas=etiquetas,
    )


@router.post("", response_model=TareaRecurrenteRead, status_code=status.HTTP_201_CREATED)
async def crear(data: TareaRecurrenteCreate, db: DbSession, actor: CurrentActor):
    """Para sí mismo, o para alguien de su departamento si es Gerente (cualquiera, el Administrador). Genera
    de inmediato la tarea del periodo en curso (y las de periodos pasados si el inicio es anterior)."""
    return await recurrente_service.crear(db, actor, data)


@router.get("/{id_recurrente}", response_model=TareaRecurrenteRead)
async def obtener(id_recurrente: int, db: DbSession, actor: CurrentActor):
    return await recurrente_service.obtener(db, actor, id_recurrente)


@router.patch("/{id_recurrente}", response_model=TareaRecurrenteRead)
async def actualizar(id_recurrente: int, data: TareaRecurrenteUpdate, db: DbSession, actor: CurrentActor):
    """Aplica a las tareas que se generen después. `activa: false` la pausa; al reanudarla se retoma en el
    periodo en curso (no se generan los que pasaron en pausa)."""
    return await recurrente_service.actualizar(db, actor, id_recurrente, data)


@router.delete("/{id_recurrente}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(id_recurrente: int, db: DbSession, actor: CurrentActor):
    """Elimina la tarea recurrente y todas las tareas que generó. Para conservarlas, pausarla."""
    await recurrente_service.eliminar(db, actor, id_recurrente)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
