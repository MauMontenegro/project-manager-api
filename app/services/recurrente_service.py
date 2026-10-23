"""Tareas recurrentes: plantillas diarias, semanales o mensuales que generan una tarea por periodo.

- Periodo: el día (solo días laborables según el calendario de Configuración), la semana (de lunes a su
  último día laborable) o el mes (del día 1 a su último día laborable). La tarea del periodo se identifica
  por su primer día (`Tarea.periodo`), así que nunca se duplica.
- Las tareas se generan al llegar su periodo (`generar`, que se invoca al consultar tareas o capacidad); los
  periodos futuros no se crean pero se proyectan en la capacidad (`carga_proyectada`).
- Son de una persona: la gestionan ella misma, el Gerente de su departamento y el Administrador; cada quien ve
  las suyas, los Gerentes las de su departamento y el Administrador todas.
- Consumen la parte de operación de la capacidad (la que no es de proyectos; ver capacidad_service).
"""
from calendar import monthrange
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.security import Actor, exigir
from app.models.configuracion import ConfiguracionLaboral
from app.models.departamento import Etiqueta
from app.models.enums import DepartamentoProyecto, EstadoTarea, Frecuencia, RolSistema, TipoRecurso
from app.models.operacion import Tarea
from app.models.organizacion import Usuario
from app.models.recurrente import TareaRecurrente
from app.schemas.recurrente import TareaRecurrenteCreate, TareaRecurrenteRead, TareaRecurrenteUpdate
from app.services import auditoria_service, configuracion_service

DIAS_ATRAS_MAX = 31
MSG_GESTION = "Solo la persona responsable, el Gerente de su departamento o el Administrador pueden gestionar sus tareas recurrentes"


# ---------- Periodos ----------
def periodo_de(frecuencia: Frecuencia, dia: date) -> date:
    if frecuencia == Frecuencia.SEMANAL:
        return dia - timedelta(days=dia.weekday())
    if frecuencia == Frecuencia.MENSUAL:
        return dia.replace(day=1)
    return dia


def siguiente(frecuencia: Frecuencia, periodo: date) -> date:
    if frecuencia == Frecuencia.SEMANAL:
        return periodo + timedelta(days=7)
    if frecuencia == Frecuencia.MENSUAL:
        return (periodo.replace(day=28) + timedelta(days=4)).replace(day=1)
    return periodo + timedelta(days=1)


def _horas_dia(config: ConfiguracionLaboral, dia: date) -> Decimal:
    """Horas del calendario laboral para ese día de la semana (sin considerar días desactivados)."""
    if dia.weekday() < 5:
        return config.horas_entre_semana
    return config.horas_sabado if dia.weekday() == 5 else Decimal(0)


def _laborable(config: ConfiguracionLaboral, dia: date) -> bool:
    return _horas_dia(config, dia) > 0 and dia not in set(config.dias_inactivos)


def _ultimo_laborable(config: ConfiguracionLaboral, desde: date, hasta: date) -> date:
    dia = hasta
    while dia > desde and _horas_dia(config, dia) <= 0:
        dia -= timedelta(days=1)
    return dia


def _rango(frecuencia: Frecuencia, periodo: date, config: ConfiguracionLaboral) -> tuple[date, date]:
    if frecuencia == Frecuencia.SEMANAL:
        return periodo, _ultimo_laborable(config, periodo, periodo + timedelta(days=6))
    if frecuencia == Frecuencia.MENSUAL:
        return periodo, _ultimo_laborable(config, periodo, periodo.replace(day=monthrange(periodo.year, periodo.month)[1]))
    return periodo, periodo


def periodos(plantilla: TareaRecurrente, config: ConfiguracionLaboral, desde: date, hasta: date) -> Iterator[tuple[date, date, date]]:
    """(periodo, inicio, fin) de los periodos de la plantilla que empiezan entre `desde` y `hasta`."""
    frecuencia = Frecuencia(plantilla.frecuencia)
    p = max(periodo_de(frecuencia, desde), periodo_de(frecuencia, plantilla.fecha_inicio))
    while p <= hasta and (plantilla.fecha_fin is None or p <= plantilla.fecha_fin):
        if frecuencia != Frecuencia.DIARIA or _laborable(config, p):
            inicio, fin = _rango(frecuencia, p, config)
            inicio = max(inicio, plantilla.fecha_inicio)
            if plantilla.fecha_fin:
                fin = min(fin, plantilla.fecha_fin)
            yield p, inicio, max(fin, inicio)
        p = siguiente(frecuencia, p)


def _pendiente_desde(plantilla: TareaRecurrente) -> date:
    """Primer periodo aún no generado."""
    frecuencia = Frecuencia(plantilla.frecuencia)
    if plantilla.generada_hasta is None:
        return periodo_de(frecuencia, plantilla.fecha_inicio)
    return siguiente(frecuencia, periodo_de(frecuencia, plantilla.generada_hasta))


# ---------- Generación ----------
async def _generar_una(db: AsyncSession, plantilla: TareaRecurrente, config: ConfiguracionLaboral, hoy: date) -> None:
    hasta = min(hoy, plantilla.fecha_fin) if plantilla.fecha_fin else hoy
    filas = [
        dict(
            id_recurrente=plantilla.id_recurrente, periodo=p, id_usuario=plantilla.id_usuario, titulo=plantilla.titulo,
            descripcion=plantilla.descripcion, horas_asignadas=plantilla.horas_por_periodo, fecha_inicio=inicio,
            fecha_fin=fin, estado=EstadoTarea.PENDIENTE.value,
        )
        for p, inicio, fin in periodos(plantilla, config, _pendiente_desde(plantilla), hasta)
    ]
    if filas:
        await db.execute(insert(Tarea).values(filas).on_conflict_do_nothing(constraint="uq_tarea_recurrente_periodo"))
    if hasta >= plantilla.fecha_inicio:
        plantilla.generada_hasta = periodo_de(Frecuencia(plantilla.frecuencia), hasta)


async def generar(db: AsyncSession) -> None:
    """Crea las tareas de los periodos que ya llegaron en las plantillas activas. Idempotente; confirma."""
    hoy = date.today()
    plantillas = list(await db.scalars(
        select(TareaRecurrente).where(
            TareaRecurrente.activa.is_(True),
            TareaRecurrente.fecha_inicio <= hoy,
            or_(TareaRecurrente.generada_hasta.is_(None), TareaRecurrente.generada_hasta < hoy),
            or_(TareaRecurrente.fecha_fin.is_(None), TareaRecurrente.generada_hasta.is_(None),
                TareaRecurrente.generada_hasta < TareaRecurrente.fecha_fin),
        )
    ))
    pendientes = [p for p in plantillas if _pendiente_desde(p) <= hoy]
    if not pendientes:
        return
    config = await configuracion_service.obtener(db)
    for plantilla in pendientes:
        await _generar_una(db, plantilla, config, hoy)
    await db.commit()


async def carga_proyectada(
    db: AsyncSession, ids_usuarios: list[int], desde: date, hasta: date,
) -> list[tuple[int, Decimal, date, date]]:
    """(id_usuario, horas, inicio, fin) de los periodos aún no generados que caen entre `desde` y `hasta`."""
    plantillas = list(await db.scalars(
        select(TareaRecurrente).where(
            TareaRecurrente.id_usuario.in_(ids_usuarios), TareaRecurrente.activa.is_(True),
            TareaRecurrente.horas_por_periodo > 0, TareaRecurrente.fecha_inicio <= hasta,
            or_(TareaRecurrente.fecha_fin.is_(None), TareaRecurrente.fecha_fin >= desde),
        )
    ))
    if not plantillas:
        return []
    config = await configuracion_service.obtener(db)
    resultado = []
    for pl in plantillas:
        # Desde el periodo que contiene `desde` (un mes puede empezar antes), sin repetir los ya generados.
        busqueda = max(_pendiente_desde(pl), periodo_de(Frecuencia(pl.frecuencia), desde))
        resultado += [(pl.id_usuario, pl.horas_por_periodo, inicio, fin)
                      for _, inicio, fin in periodos(pl, config, busqueda, hasta) if fin >= desde]
    return resultado


# ---------- Permisos y visibilidad ----------
def gestiona_persona(actor: Actor, usuario: Usuario) -> bool:
    return actor.id_usuario == usuario.id_usuario or actor.gestiona_departamento(usuario.departamento)


def filtro_visibles(actor: Actor):
    """Condición sobre `Usuario` (unido a la consulta) con las personas cuyas tareas recurrentes ve el actor."""
    if actor.es_admin:
        return True
    propias = Usuario.id_usuario == actor.id_usuario
    if actor.rol == RolSistema.GERENTE:
        return or_(propias, Usuario.departamento == actor.departamento)
    return propias


async def involucrados(db: AsyncSession, tarea: Tarea) -> list[Usuario]:
    """Pueden comentar y ser mencionados: el responsable y los Gerentes de su departamento."""
    responsable = await db.get(Usuario, tarea.id_usuario)
    gerentes = list(await db.scalars(
        select(Usuario).where(
            Usuario.activo.is_(True), Usuario.rol == RolSistema.GERENTE.value,
            Usuario.departamento == responsable.departamento, Usuario.id_usuario != responsable.id_usuario,
        ).order_by(Usuario.nombre)
    )) if responsable and responsable.departamento else []
    return ([responsable] if responsable and responsable.activo else []) + gerentes


# ---------- Plantillas ----------
async def _responsable(db: AsyncSession, id_usuario: int) -> Usuario:
    usuario = await db.get(Usuario, id_usuario)
    if usuario is None:
        raise NotFoundError(f"Usuario con id {id_usuario} no existe")
    if not usuario.activo or usuario.tipo_recurso == TipoRecurso.ACTIVO.value:
        raise BusinessRuleError(f"'{usuario.nombre}' no puede tener tareas (inactivo o es un activo)")
    return usuario


async def _etiquetas(db: AsyncSession, ids: list[int], responsable: Usuario) -> list[Etiqueta]:
    """Del catálogo del departamento del responsable (de cualquiera si su departamento no tiene catálogo)."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    etiquetas = list(await db.scalars(select(Etiqueta).where(Etiqueta.id_etiqueta.in_(ids))))
    faltantes = set(ids) - {e.id_etiqueta for e in etiquetas}
    if faltantes:
        raise NotFoundError(f"Etiquetas inexistentes: {sorted(faltantes)}")
    if responsable.departamento in [d.value for d in DepartamentoProyecto]:
        ajenas = [e.nombre for e in etiquetas if e.departamento != responsable.departamento]
        if ajenas:
            raise BusinessRuleError(f"Las etiquetas {', '.join(ajenas)} no son de {responsable.departamento}")
    return etiquetas


async def _obtener(db: AsyncSession, id_recurrente: int) -> TareaRecurrente:
    plantilla = await db.scalar(
        select(TareaRecurrente).where(TareaRecurrente.id_recurrente == id_recurrente)
        .options(selectinload(TareaRecurrente.etiquetas), selectinload(TareaRecurrente.usuario))
        .execution_options(populate_existing=True)
    )
    if plantilla is None:
        raise NotFoundError(f"Tarea recurrente con id {id_recurrente} no existe")
    return plantilla


async def _leer(db: AsyncSession, plantillas: list[TareaRecurrente]) -> list[TareaRecurrenteRead]:
    ids = [p.id_recurrente for p in plantillas]
    abiertas = dict((await db.execute(
        select(Tarea.id_recurrente, func.count()).where(
            Tarea.id_recurrente.in_(ids), Tarea.estado != EstadoTarea.FINALIZADO.value
        ).group_by(Tarea.id_recurrente)
    )).all()) if ids else {}
    return [
        TareaRecurrenteRead.model_validate(p).model_copy(update={"tareas_abiertas": abiertas.get(p.id_recurrente, 0)})
        for p in plantillas
    ]


async def listar(
    db: AsyncSession, actor: Actor, *, id_usuario: int | None = None, departamento: str | None = None,
    frecuencia: Frecuencia | None = None, activa: bool | None = None, etiquetas: list[int] | None = None,
) -> list[TareaRecurrenteRead]:
    stmt = (
        select(TareaRecurrente).join(Usuario, Usuario.id_usuario == TareaRecurrente.id_usuario)
        .where(filtro_visibles(actor)).options(selectinload(TareaRecurrente.etiquetas))
    )
    if id_usuario is not None:
        stmt = stmt.where(TareaRecurrente.id_usuario == id_usuario)
    if departamento is not None:
        stmt = stmt.where(Usuario.departamento == departamento)
    if frecuencia is not None:
        stmt = stmt.where(TareaRecurrente.frecuencia == frecuencia.value)
    if activa is not None:
        stmt = stmt.where(TareaRecurrente.activa.is_(activa))
    if etiquetas:
        stmt = stmt.where(TareaRecurrente.etiquetas.any(Etiqueta.id_etiqueta.in_(etiquetas)))
    plantillas = list(await db.scalars(stmt.order_by(TareaRecurrente.activa.desc(), TareaRecurrente.titulo)))
    return await _leer(db, plantillas)


async def obtener(db: AsyncSession, actor: Actor, id_recurrente: int) -> TareaRecurrenteRead:
    plantilla = await _obtener(db, id_recurrente)
    exigir(gestiona_persona(actor, plantilla.usuario) or actor.gestiona_equipo, "No puedes ver esta tarea recurrente")
    return (await _leer(db, [plantilla]))[0]


async def crear(db: AsyncSession, actor: Actor, data: TareaRecurrenteCreate) -> TareaRecurrenteRead:
    responsable = await _responsable(db, data.id_usuario)
    exigir(gestiona_persona(actor, responsable), MSG_GESTION)
    if data.fecha_inicio < date.today() - timedelta(days=DIAS_ATRAS_MAX):
        raise BusinessRuleError(f"El inicio no puede ser de hace más de {DIAS_ATRAS_MAX} días")
    plantilla = TareaRecurrente(
        **data.model_dump(exclude={"etiquetas", "frecuencia"}), frecuencia=data.frecuencia.value,
        id_creador=actor.id_usuario,
    )
    plantilla.etiquetas = await _etiquetas(db, data.etiquetas, responsable)
    db.add(plantilla)
    await db.flush()
    auditoria_service.registrar(
        db, actor, entidad="tarea_recurrente", id_entidad=plantilla.id_recurrente, id_usuario_afectado=responsable.id_usuario,
        accion="alta", resumen=f"Tarea recurrente «{plantilla.titulo}» ({plantilla.frecuencia.lower()}) para {responsable.nombre}",
    )
    await _generar_una(db, plantilla, await configuracion_service.obtener(db), date.today())
    await db.commit()
    return await obtener(db, actor, plantilla.id_recurrente)


async def actualizar(db: AsyncSession, actor: Actor, id_recurrente: int, data: TareaRecurrenteUpdate) -> TareaRecurrenteRead:
    plantilla = await _obtener(db, id_recurrente)
    exigir(gestiona_persona(actor, plantilla.usuario), MSG_GESTION)
    cambios = data.model_dump(exclude_unset=True)
    for campo in ("titulo", "id_usuario", "horas_por_periodo", "activa", "etiquetas"):
        if campo in cambios and cambios[campo] is None:
            raise BusinessRuleError(f"{campo} no puede ser nulo")

    responsable = plantilla.usuario
    if "id_usuario" in cambios and cambios["id_usuario"] != plantilla.id_usuario:
        responsable = await _responsable(db, cambios["id_usuario"])
        exigir(gestiona_persona(actor, responsable), MSG_GESTION)
    if "etiquetas" in cambios:
        plantilla.etiquetas = await _etiquetas(db, cambios.pop("etiquetas"), responsable)
    elif responsable is not plantilla.usuario:  # las del departamento anterior dejan de aplicar
        plantilla.etiquetas = [e for e in plantilla.etiquetas if e.departamento == responsable.departamento]

    reactivada = cambios.get("activa") is True and not plantilla.activa
    for campo, valor in cambios.items():
        setattr(plantilla, campo, valor)
    if plantilla.fecha_fin and plantilla.fecha_fin < plantilla.fecha_inicio:
        raise BusinessRuleError("fecha_fin no puede ser anterior a fecha_inicio")
    if reactivada:
        # No se generan los periodos que pasaron mientras estuvo pausada: se retoma en el actual.
        hoy = date.today()
        if plantilla.generada_hasta is not None:
            plantilla.generada_hasta = max(plantilla.generada_hasta, periodo_de(Frecuencia(plantilla.frecuencia), hoy) - timedelta(days=1))
        await _generar_una(db, plantilla, await configuracion_service.obtener(db), hoy)

    auditoria_service.registrar(
        db, actor, entidad="tarea_recurrente", id_entidad=id_recurrente, id_usuario_afectado=plantilla.id_usuario,
        accion="edicion", resumen=f"Tarea recurrente «{plantilla.titulo}» actualizada"
        + (" (pausada)" if cambios.get("activa") is False else " (reanudada)" if reactivada else ""),
    )
    await db.commit()
    return await obtener(db, actor, id_recurrente)


async def eliminar(db: AsyncSession, actor: Actor, id_recurrente: int) -> None:
    """Borra la plantilla y todas las tareas que generó (para conservarlas, pausarla)."""
    plantilla = await _obtener(db, id_recurrente)
    exigir(gestiona_persona(actor, plantilla.usuario), MSG_GESTION)
    auditoria_service.registrar(
        db, actor, entidad="tarea_recurrente", id_entidad=id_recurrente, id_usuario_afectado=plantilla.id_usuario,
        accion="baja", resumen=f"Tarea recurrente «{plantilla.titulo}» eliminada con sus tareas",
    )
    await db.delete(plantilla)
    await db.commit()
