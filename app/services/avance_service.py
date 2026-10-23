"""Avance del proyecto calculado a partir de las tareas.

- Cada una de las n etapas del proyecto vale 100 % / n. Su aporte = peso × tareas finalizadas / tareas de la etapa.
- Una etapa sin tareas aporta su peso completo si ya se pasó y 0 % si es la actual o posterior.
- Un proyecto `Completado` está al 100 %.
- Avance automático (solo ante cambios en tareas): cuando todas las tareas de la etapa actual
  están finalizadas, el proyecto pasa a la siguiente etapa como `Activo`; en la última etapa
  queda `Completado`. Además, un proyecto `Sin Iniciar` pasa a `Activo` en cuanto una tarea se mueve.
"""
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ciclo_vida import ESTADOS_FINALES, peso_etapa
from app.models.enums import EstadoProyecto, EstadoTarea
from app.models.operacion import EtapaProyecto, Tarea
from app.models.proyecto import Proyecto
from app.services import conjunto_service, semaforo_service

CIEN = Decimal("100.00")


def sincronizar_etapas(etapas: Iterable[EtapaProyecto], orden_actual: int, estado: EstadoProyecto) -> None:
    """Anteriores `Completado`, la actual con el estatus del proyecto y las posteriores `Sin Iniciar`."""
    for etapa in etapas:
        if etapa.orden_secuencia < orden_actual:
            etapa.estado_etapa = EstadoProyecto.COMPLETADO.value
        elif etapa.orden_secuencia == orden_actual:
            etapa.estado_etapa = estado.value
        else:
            etapa.estado_etapa = EstadoProyecto.SIN_INICIAR.value


def calcular_avance(
    conteos: dict[int, tuple[int, int]], ordenes: Iterable[int], orden_actual: int, estado: EstadoProyecto
) -> Decimal:
    """`conteos`: orden de etapa → (tareas, finalizadas). `ordenes`: los de todas las etapas del proyecto."""
    if estado == EstadoProyecto.COMPLETADO:
        return CIEN
    ordenes = list(ordenes)
    peso = peso_etapa(len(ordenes))
    avance = Decimal(0)
    for orden in ordenes:
        total, finalizadas = conteos.get(orden, (0, 0))
        if total:
            avance += peso * Decimal(finalizadas) / Decimal(total)
        elif orden < orden_actual:
            avance += peso
    return min(avance, CIEN).quantize(Decimal("0.01"))


async def conteos_por_etapa(db: AsyncSession, id_proyecto: int) -> dict[int, tuple[int, int]]:
    finalizada = case((Tarea.estado == EstadoTarea.FINALIZADO.value, 1), else_=0)
    filas = await db.execute(
        select(EtapaProyecto.orden_secuencia, func.count(Tarea.id_tarea), func.coalesce(func.sum(finalizada), 0))
        .join(Tarea, Tarea.id_etapa == EtapaProyecto.id_etapa)
        .where(EtapaProyecto.id_proyecto == id_proyecto)
        .group_by(EtapaProyecto.orden_secuencia)
    )
    return {orden: (total, int(fin)) for orden, total, fin in filas}


async def recalcular(db: AsyncSession, proyecto: Proyecto, *, por_tareas: bool) -> None:
    """Recalcula avance, etapa (si `por_tareas`) y semáforo. No confirma la transacción.

    `por_tareas=False` se usa en los cambios manuales de ciclo: así regresar a una etapa con todas sus
    tareas finalizadas no hace que el proyecto vuelva a avanzar solo."""
    await db.flush()
    etapas = list(await db.scalars(
        select(EtapaProyecto).where(EtapaProyecto.id_proyecto == proyecto.id_proyecto).order_by(EtapaProyecto.orden_secuencia)
    ))
    if not etapas:  # conjunto: se consolida a partir de sus subproyectos
        return
    conteos = await conteos_por_etapa(db, proyecto.id_proyecto)
    estado = EstadoProyecto(proyecto.estado_proyecto)
    orden = next((e.orden_secuencia for e in etapas if e.nombre_etapa == proyecto.etapa_actual), etapas[0].orden_secuencia)
    ordenes = [e.orden_secuencia for e in etapas]

    if por_tareas and estado not in ESTADOS_FINALES:
        if estado == EstadoProyecto.SIN_INICIAR:
            tareas_movidas = await db.scalar(
                select(func.count()).where(
                    Tarea.id_proyecto == proyecto.id_proyecto, Tarea.estado != EstadoTarea.PENDIENTE.value
                )
            )
            if tareas_movidas:
                estado = EstadoProyecto.ACTIVO
        while True:
            total, finalizadas = conteos.get(orden, (0, 0))
            if not total or finalizadas < total:
                break
            if orden == ordenes[-1]:
                estado = EstadoProyecto.COMPLETADO
                proyecto.fecha_real_cierre = date.today()
                break
            orden, estado = ordenes[ordenes.index(orden) + 1], EstadoProyecto.ACTIVO

    proyecto.etapa_actual = next(e.nombre_etapa for e in etapas if e.orden_secuencia == orden)
    proyecto.estado_proyecto = estado.value
    proyecto.porcentaje_avance = calcular_avance(conteos, ordenes, orden, estado)

    sincronizar_etapas(etapas, orden, estado)
    semaforo_service.aplicar(proyecto, etapas)
    await conjunto_service.consolidar_padre_de(db, proyecto)
