"""Semáforo calculado: compara el avance real con el esperado según las fechas.

- Avance esperado a hoy: cada etapa con fechas estimadas cubre su rango de avance
  (p. ej. la 3.ª de 5, 40–60 %) de forma lineal entre su inicio y su fin.
- Rojo: fecha comprometida vencida sin completar, o avance ≥ 15 puntos por debajo del esperado.
- Amarillo: avance entre 5 y 15 puntos por debajo, o la fecha comprometida está a ≤ 14 días y el
  proyecto aún no llega a la última etapa.
- Verde: en cualquier otro caso.
Un proyecto `Completado` queda en Verde, o en Rojo si cerró después de la fecha comprometida. Uno
`Cancelado` conserva su último semáforo.

Como depende de la fecha, se recalcula al guardar y, una vez al día, al consultar.
"""
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ciclo_vida import peso_etapa
from app.models.enums import EstadoProyecto, Semaforo
from app.models.operacion import EtapaProyecto
from app.models.proyecto import Proyecto
from app.services import conjunto_service

DESFASE_AMARILLO = Decimal(5)
DESFASE_ROJO = Decimal(15)
DIAS_AVISO_COMPROMISO = 14


def avance_esperado(etapas: Sequence[EtapaProyecto], hoy: date) -> Decimal | None:
    """Avance que debería llevar el proyecto hoy según el plan; `None` si ninguna etapa tiene fechas."""
    esperado: Decimal | None = None
    peso = peso_etapa(len(etapas))
    for i, etapa in enumerate(sorted(etapas, key=lambda e: e.orden_secuencia)):
        inicio, fin = etapa.fecha_inicio_est, etapa.fecha_fin_est
        if inicio is None or fin is None:
            continue
        piso, techo = peso * i, peso * (i + 1)
        if hoy < inicio:
            valor = Decimal(0)
        elif hoy >= fin:
            valor = techo
        else:
            fraccion = Decimal((hoy - inicio).days) / Decimal((fin - inicio).days)
            valor = piso + (techo - piso) * fraccion
        esperado = valor if esperado is None else max(esperado, valor)
    return esperado.quantize(Decimal(1), ROUND_HALF_UP) if esperado is not None else None


def calcular(proyecto: Proyecto, etapas: Sequence[EtapaProyecto], hoy: date) -> tuple[Semaforo, str]:
    estado = EstadoProyecto(proyecto.estado_proyecto)
    comprometida = proyecto.fecha_comprometida
    real = proyecto.porcentaje_avance.quantize(Decimal(1), ROUND_HALF_UP)

    if estado == EstadoProyecto.COMPLETADO:
        cierre = proyecto.fecha_real_cierre or hoy
        if comprometida and cierre > comprometida:
            return Semaforo.ROJO, f"Cerró {(cierre - comprometida).days} días después de la fecha comprometida"
        return Semaforo.VERDE, "Completado a tiempo" if comprometida else "Completado"

    if comprometida and hoy > comprometida:
        return Semaforo.ROJO, f"Fecha comprometida vencida hace {(hoy - comprometida).days} días ({real} % de avance)"

    esperado = avance_esperado(etapas, hoy)
    if esperado is not None:
        desfase = esperado - real
        detalle = f"Avance {real} % vs. {esperado} % esperado"
        if desfase >= DESFASE_ROJO:
            return Semaforo.ROJO, detalle
        if desfase >= DESFASE_AMARILLO:
            return Semaforo.AMARILLO, detalle

    ultima = max(etapas, key=lambda e: e.orden_secuencia).nombre_etapa if etapas else None
    if comprometida and (comprometida - hoy).days <= DIAS_AVISO_COMPROMISO and ultima and proyecto.etapa_actual != ultima:
        return Semaforo.AMARILLO, f"Faltan {(comprometida - hoy).days} días para la fecha comprometida y aún no está en '{ultima}'"

    if esperado is not None:
        return Semaforo.VERDE, f"Avance {real} % vs. {esperado} % esperado"
    if comprometida:
        return Semaforo.VERDE, "En plazo (sin fechas en las etapas para medir el avance esperado)"
    return Semaforo.VERDE, "Sin fechas planificadas para evaluar"


def aplicar(proyecto: Proyecto, etapas: Sequence[EtapaProyecto], hoy: date | None = None) -> None:
    """Recalcula y guarda el semáforo en el proyecto (salvo si está cancelado: se congela)."""
    hoy = hoy or date.today()
    if proyecto.estado_proyecto != EstadoProyecto.CANCELADO.value:
        semaforo, motivo = calcular(proyecto, etapas, hoy)
        proyecto.semaforo, proyecto.semaforo_motivo = semaforo.value, motivo
    proyecto.semaforo_fecha = hoy


async def recalcular(db: AsyncSession, proyecto: Proyecto) -> None:
    """Recalcula un proyecto con sus etapas tal como están en la sesión (sin confirmar)."""
    await db.flush()
    if proyecto.es_conjunto:
        await conjunto_service.consolidar(db, proyecto)
        return
    etapas = list(await db.scalars(select(EtapaProyecto).where(EtapaProyecto.id_proyecto == proyecto.id_proyecto)))
    aplicar(proyecto, etapas)
    await conjunto_service.consolidar_padre_de(db, proyecto)


async def refrescar_vencidos(db: AsyncSession) -> None:
    """Recalcula los proyectos abiertos cuyo semáforo no se ha evaluado hoy."""
    hoy = date.today()
    pendientes = await db.scalars(
        select(Proyecto)
        .where(
            Proyecto.estado_proyecto.not_in([EstadoProyecto.COMPLETADO.value, EstadoProyecto.CANCELADO.value]),
            Proyecto.es_conjunto.is_(False),
            or_(Proyecto.semaforo_fecha.is_(None), Proyecto.semaforo_fecha < hoy),
        )
        .options(selectinload(Proyecto.etapas))
    )
    hubo, padres = False, set()
    for proyecto in pendientes:
        aplicar(proyecto, proyecto.etapas, hoy)
        hubo = True
        if proyecto.id_proyecto_padre is not None:
            padres.add(proyecto.id_proyecto_padre)
    for id_padre in padres:
        await conjunto_service.consolidar(db, await db.get(Proyecto, id_padre))
    if hubo:
        await db.commit()
