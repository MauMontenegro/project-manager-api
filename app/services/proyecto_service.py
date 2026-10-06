from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.models.demanda import SolicitudDemanda
from app.models.enums import EstadoDemanda, EstadoProyecto, Semaforo
from app.models.operacion import EtapaProyecto
from app.models.organizacion import Empresa, Usuario
from app.models.proyecto import Proyecto
from app.models.tablas_uniones import AsignacionRecurso, ProyectoEmpresaImpactada
from app.schemas.proyecto import (
    AsignacionCreate,
    EtapaCreate,
    ProyectoCambioEstado,
    ProyectoCreate,
    ProyectoUpdate,
)

TRANSICIONES_ESTADO: dict[EstadoProyecto, set[EstadoProyecto]] = {
    EstadoProyecto.INICIACION: {EstadoProyecto.PLANEACION, EstadoProyecto.PAUSADO, EstadoProyecto.CANCELADO},
    EstadoProyecto.PLANEACION: {EstadoProyecto.EJECUCION, EstadoProyecto.PAUSADO, EstadoProyecto.CANCELADO},
    EstadoProyecto.EJECUCION: {EstadoProyecto.CIERRE, EstadoProyecto.PAUSADO, EstadoProyecto.CANCELADO},
    EstadoProyecto.PAUSADO: {EstadoProyecto.PLANEACION, EstadoProyecto.EJECUCION, EstadoProyecto.CANCELADO},
    EstadoProyecto.CIERRE: set(),
    EstadoProyecto.CANCELADO: set(),
}

ESTADOS_SIN_ASIGNACION = {EstadoProyecto.CIERRE, EstadoProyecto.CANCELADO}


async def _usuario_activo(db: AsyncSession, id_usuario: int, rol: str) -> Usuario:
    usuario = await db.get(Usuario, id_usuario)
    if usuario is None:
        raise NotFoundError(f"{rol} con id {id_usuario} no existe")
    if not usuario.activo:
        raise BusinessRuleError(f"{rol} con id {id_usuario} está inactivo")
    return usuario


async def obtener_proyecto(db: AsyncSession, id_proyecto: int) -> Proyecto:
    stmt = (
        select(Proyecto)
        .where(Proyecto.id_proyecto == id_proyecto)
        .options(selectinload(Proyecto.empresas_impactadas))
        .execution_options(populate_existing=True)
    )
    proyecto = await db.scalar(stmt)
    if proyecto is None:
        raise NotFoundError(f"Proyecto con id {id_proyecto} no existe")
    return proyecto


async def crear_proyecto(db: AsyncSession, data: ProyectoCreate) -> Proyecto:
    await _usuario_activo(db, data.lider_id, "Líder")

    solicitud: SolicitudDemanda | None = None
    if data.id_solicitud is not None:
        solicitud = await db.get(SolicitudDemanda, data.id_solicitud)
        if solicitud is None:
            raise NotFoundError(f"Solicitud con id {data.id_solicitud} no existe")
        ya_usada = await db.scalar(select(Proyecto.id_proyecto).where(Proyecto.id_solicitud == data.id_solicitud))
        if ya_usada is not None:
            raise ConflictError(f"La solicitud {data.id_solicitud} ya está asociada al proyecto {ya_usada}")

    ids_empresas = {e.id_empresa for e in data.empresas_impactadas}
    if ids_empresas:
        encontradas = set(await db.scalars(select(Empresa.id_empresa).where(Empresa.id_empresa.in_(ids_empresas))))
        faltantes = ids_empresas - encontradas
        if faltantes:
            raise NotFoundError(f"Empresas inexistentes: {sorted(faltantes)}")

    proyecto = Proyecto(
        **data.model_dump(exclude={"empresas_impactadas"}),
        estado_proyecto=EstadoProyecto.INICIACION.value,
    )
    proyecto.empresas_impactadas = [ProyectoEmpresaImpactada(**e.model_dump()) for e in data.empresas_impactadas]
    db.add(proyecto)

    if solicitud is not None:
        solicitud.estado_demanda = EstadoDemanda.EN_EJECUCION.value

    await db.commit()
    return await obtener_proyecto(db, proyecto.id_proyecto)


async def actualizar_proyecto(db: AsyncSession, id_proyecto: int, data: ProyectoUpdate) -> Proyecto:
    proyecto = await obtener_proyecto(db, id_proyecto)
    cambios = data.model_dump(exclude_unset=True)

    for campo in ("nombre_proyecto", "problema_oportunidad", "objetivo", "alcance", "fuera_de_alcance", "semaforo", "lider_id"):
        if campo in cambios and cambios[campo] is None:
            raise BusinessRuleError(f"{campo} no puede ser nulo")

    if "lider_id" in cambios:
        await _usuario_activo(db, cambios["lider_id"], "Líder")

    for campo, valor in cambios.items():
        setattr(proyecto, campo, valor)

    await db.commit()
    return await obtener_proyecto(db, id_proyecto)


async def cambiar_estado(db: AsyncSession, id_proyecto: int, data: ProyectoCambioEstado) -> Proyecto:
    proyecto = await obtener_proyecto(db, id_proyecto)
    actual = EstadoProyecto(proyecto.estado_proyecto)
    nuevo = data.estado_proyecto

    if nuevo not in TRANSICIONES_ESTADO[actual]:
        permitidos = ", ".join(sorted(e.value for e in TRANSICIONES_ESTADO[actual])) or "ninguno"
        raise BusinessRuleError(
            f"Transición no permitida: '{actual.value}' → '{nuevo.value}'. Estados permitidos: {permitidos}"
        )

    proyecto.estado_proyecto = nuevo.value
    if nuevo == EstadoProyecto.CIERRE:
        proyecto.fecha_real_cierre = data.fecha_real_cierre or date.today()

    await db.commit()
    return await obtener_proyecto(db, id_proyecto)


async def listar_portafolio(
    db: AsyncSession,
    *,
    semaforo: Semaforo | None = None,
    id_empresa: int | None = None,
    estado: EstadoProyecto | None = None,
    lider_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Proyecto], int]:
    """Portafolio filtrable. Una empresa se considera vinculada a un proyecto si es una de las
    empresas impactadas o si es la empresa solicitante de la demanda de origen."""
    filtros = []
    if semaforo is not None:
        filtros.append(Proyecto.semaforo == semaforo.value)
    if estado is not None:
        filtros.append(Proyecto.estado_proyecto == estado.value)
    if lider_id is not None:
        filtros.append(Proyecto.lider_id == lider_id)
    if id_empresa is not None:
        filtros.append(
            or_(
                Proyecto.empresas_impactadas.any(ProyectoEmpresaImpactada.id_empresa == id_empresa),
                Proyecto.solicitud.has(SolicitudDemanda.id_empresa == id_empresa),
            )
        )

    total = await db.scalar(select(func.count()).select_from(Proyecto).where(*filtros))
    result = await db.scalars(
        select(Proyecto).where(*filtros).order_by(Proyecto.id_proyecto.desc()).limit(limit).offset(offset)
    )
    return list(result), total or 0


async def crear_etapa(db: AsyncSession, id_proyecto: int, data: EtapaCreate) -> EtapaProyecto:
    await obtener_proyecto(db, id_proyecto)
    existe = await db.scalar(
        select(EtapaProyecto.id_etapa).where(
            EtapaProyecto.id_proyecto == id_proyecto, EtapaProyecto.orden_secuencia == data.orden_secuencia
        )
    )
    if existe is not None:
        raise ConflictError(f"El proyecto ya tiene una etapa con orden_secuencia {data.orden_secuencia}")

    etapa = EtapaProyecto(id_proyecto=id_proyecto, **data.model_dump())
    db.add(etapa)
    await db.commit()
    await db.refresh(etapa)
    return etapa


async def listar_etapas(db: AsyncSession, id_proyecto: int) -> list[EtapaProyecto]:
    await obtener_proyecto(db, id_proyecto)
    result = await db.scalars(
        select(EtapaProyecto).where(EtapaProyecto.id_proyecto == id_proyecto).order_by(EtapaProyecto.orden_secuencia)
    )
    return list(result)


async def asignar_recurso(db: AsyncSession, id_proyecto: int, data: AsignacionCreate) -> AsignacionRecurso:
    proyecto = await obtener_proyecto(db, id_proyecto)
    if EstadoProyecto(proyecto.estado_proyecto) in ESTADOS_SIN_ASIGNACION:
        raise BusinessRuleError(f"No se pueden asignar recursos a un proyecto en estado '{proyecto.estado_proyecto}'")

    etapa = await db.get(EtapaProyecto, data.id_etapa)
    if etapa is None or etapa.id_proyecto != id_proyecto:
        raise NotFoundError(f"La etapa {data.id_etapa} no existe en el proyecto {id_proyecto}")

    await _usuario_activo(db, data.id_usuario, "Usuario")

    duplicada = await db.scalar(
        select(AsignacionRecurso.id_asignacion).where(
            AsignacionRecurso.id_usuario == data.id_usuario, AsignacionRecurso.id_etapa == data.id_etapa
        )
    )
    if duplicada is not None:
        raise ConflictError(f"El usuario {data.id_usuario} ya está asignado a la etapa {data.id_etapa}")

    asignacion = AsignacionRecurso(id_proyecto=id_proyecto, **data.model_dump())
    db.add(asignacion)
    await db.commit()
    await db.refresh(asignacion)
    return asignacion


async def listar_asignaciones(db: AsyncSession, id_proyecto: int) -> list[AsignacionRecurso]:
    await obtener_proyecto(db, id_proyecto)
    result = await db.scalars(
        select(AsignacionRecurso).where(AsignacionRecurso.id_proyecto == id_proyecto).order_by(AsignacionRecurso.id_asignacion)
    )
    return list(result)
