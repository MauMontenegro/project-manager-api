from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActor
from app.models.enums import DepartamentoProyecto, EstadoProyecto, Semaforo
from app.schemas.proyecto import (
    AsignacionCreate,
    AsignacionRead,
    EtapaRead,
    EtapaUpdate,
    PortafolioPage,
    ProyectoCambioEstado,
    ProyectoCreate,
    ProyectoDetalle,
    ProyectoUpdate,
    SubproyectoIn,
)
from app.services import proyecto_service, semaforo_service, visibilidad

router = APIRouter(prefix="/proyectos", tags=["Proyectos"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=ProyectoDetalle, status_code=status.HTTP_201_CREATED)
async def crear_proyecto(data: ProyectoCreate, db: DbSession, actor: CurrentActor):
    """Crea un proyecto 'Sin Iniciar' (0 %) en la primera etapa de su departamento, con las etapas de su
    plantilla (Gerente del departamento o Administrador). Un conjunto (cualquier Gerente) crea además un
    subproyecto por departamento participante. Si proviene de una solicitud de demanda, esta pasa a 'En Ejecución'."""
    return await proyecto_service.crear_proyecto(db, actor, data)


@router.get("", response_model=PortafolioPage)
async def consultar_portafolio(
    db: DbSession,
    actor: CurrentActor,
    departamento: Annotated[
        DepartamentoProyecto | None, Query(description="Espacio: sus proyectos y los conjuntos en que participa")
    ] = None,
    semaforo: Semaforo | None = None,
    id_empresa: Annotated[int | None, Query(description="Empresa impactada o solicitante")] = None,
    estado: EstadoProyecto | None = None,
    etapa: Annotated[str | None, Query(description="Nombre de la etapa actual")] = None,
    lider_id: int | None = None,
    etiquetas: Annotated[list[int] | None, Query(description="Con cualquiera de estas etiquetas")] = None,
    id_equipo_trabajo: Annotated[int | None, Query(description="Solo los de ese equipo de trabajo")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Portafolio de primer nivel (los conjuntos traen sus subproyectos) con filtros por departamento,
    semáforo, empresa, estatus, etapa actual, líder, etiquetas y equipo de trabajo. Solo los que el rol puede ver."""
    await semaforo_service.refrescar_vencidos(db)
    items, total = await proyecto_service.listar_portafolio(
        db, departamento=departamento, semaforo=semaforo, id_empresa=id_empresa, estado=estado, etapa=etapa,
        lider_id=lider_id, etiquetas=etiquetas, id_equipo_trabajo=id_equipo_trabajo, limit=limit, offset=offset,
        visibles=visibilidad.condicion(actor),
    )
    return PortafolioPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{id_proyecto}", response_model=ProyectoDetalle)
async def obtener_proyecto(id_proyecto: int, db: DbSession, actor: CurrentActor):
    await visibilidad.exigir_proyecto(db, actor, id_proyecto)
    await semaforo_service.refrescar_vencidos(db)
    return await proyecto_service.obtener_proyecto(db, id_proyecto)


@router.patch("/{id_proyecto}", response_model=ProyectoDetalle)
async def actualizar_proyecto(id_proyecto: int, data: ProyectoUpdate, db: DbSession, actor: CurrentActor):
    """Líder, Gerente del departamento o Administrador. En un conjunto (solo su líder o el Administrador), las fechas
    y el presupuesto no se editan: se consolidan de los subproyectos."""
    return await proyecto_service.actualizar_proyecto(db, actor, id_proyecto, data)


@router.delete("/{id_proyecto}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_proyecto(id_proyecto: int, db: DbSession, actor: CurrentActor):
    """Elimina el proyecto de forma permanente, con sus etapas, asignaciones, bloqueos y demás registros.
    Un conjunto se elimina con sus subproyectos. Solo el Administrador."""
    await proyecto_service.eliminar_proyecto(db, actor, id_proyecto)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{id_proyecto}/subproyectos", response_model=ProyectoDetalle, status_code=status.HTTP_201_CREATED)
async def agregar_subproyecto(id_proyecto: int, data: SubproyectoIn, db: DbSession, actor: CurrentActor):
    """Suma un departamento a un proyecto conjunto. Devuelve el conjunto."""
    return await proyecto_service.agregar_subproyecto(db, actor, id_proyecto, data)


@router.delete("/{id_proyecto}/subproyectos/{id_subproyecto}", response_model=ProyectoDetalle)
async def quitar_subproyecto(id_proyecto: int, id_subproyecto: int, db: DbSession, actor: CurrentActor):
    """Quita un departamento del conjunto si su subproyecto aún no tiene tareas. Devuelve el conjunto."""
    return await proyecto_service.quitar_subproyecto(db, actor, id_proyecto, id_subproyecto)


@router.patch("/{id_proyecto}/estado", response_model=ProyectoDetalle)
async def cambiar_estado(id_proyecto: int, data: ProyectoCambioEstado, db: DbSession, actor: CurrentActor):
    """Cambia etapa actual y/o estatus validando las reglas del ciclo de vida."""
    return await proyecto_service.cambiar_estado(db, actor, id_proyecto, data)


@router.patch("/{id_proyecto}/etapas/{id_etapa}", response_model=EtapaRead)
async def actualizar_etapa(id_proyecto: int, id_etapa: int, data: EtapaUpdate, db: DbSession, actor: CurrentActor):
    """Planifica horas y fechas de una etapa. El estatus lo sincroniza `PATCH /proyectos/{id}/estado`."""
    return await proyecto_service.actualizar_etapa(db, actor, id_proyecto, id_etapa, data)


@router.get("/{id_proyecto}/etapas", response_model=list[EtapaRead])
async def listar_etapas(id_proyecto: int, db: DbSession, actor: CurrentActor):
    await visibilidad.exigir_proyecto(db, actor, id_proyecto)
    return await proyecto_service.listar_etapas(db, id_proyecto)


@router.post("/{id_proyecto}/asignaciones", response_model=AsignacionRead, status_code=status.HTTP_201_CREATED)
async def asignar_recurso(id_proyecto: int, data: AsignacionCreate, db: DbSession, actor: CurrentActor):
    """Asigna un usuario activo a una etapa. Solo el líder del proyecto, Gerentes o el Administrador."""
    return await proyecto_service.asignar_recurso(db, actor, id_proyecto, data)


@router.get("/{id_proyecto}/asignaciones", response_model=list[AsignacionRead])
async def listar_asignaciones(id_proyecto: int, db: DbSession, actor: CurrentActor):
    await visibilidad.exigir_proyecto(db, actor, id_proyecto)
    return await proyecto_service.listar_asignaciones(db, id_proyecto)
