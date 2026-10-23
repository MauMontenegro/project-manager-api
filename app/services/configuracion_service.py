"""Calendario laboral (fila única) y cálculo automático de las horas presupuestadas de los proyectos.

Horas presupuestadas = Σ horas de cada día entre el inicio y el fin del proyecto (ambos incluidos):
lunes a viernes `horas_entre_semana`, sábado `horas_sabado`, domingo 0, y 0 en los días desactivados. Si falta alguna fecha, el proyecto queda sin límite.
Un presupuesto fijado a mano (`horas_presupuestadas_manual`) no se recalcula.
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Actor, exigir
from app.models.ciclo_vida import ESTADOS_FINALES
from app.models.configuracion import ConfiguracionLaboral
from app.models.operacion import Tarea
from app.models.proyecto import Proyecto
from app.services import conjunto_service
from app.schemas.configuracion import ConfiguracionGuardada, ConfiguracionLaboralIn, ConfiguracionLaboralRead


async def obtener(db: AsyncSession) -> ConfiguracionLaboral:
    config = await db.get(ConfiguracionLaboral, 1)
    if config is None:  # base nueva: se crea con los valores por defecto
        config = ConfiguracionLaboral(id=1)
        db.add(config)
        await db.flush()
    return config


def horas_laborales(config: ConfiguracionLaboral, desde: date, hasta: date) -> tuple[Decimal, int]:
    """(horas, días laborables) entre `desde` y `hasta`, ambos incluidos."""
    por_dia = [config.horas_entre_semana] * 5 + [config.horas_sabado, Decimal(0)]  # lunes = 0 … domingo = 6
    inactivos = set(config.dias_inactivos)
    horas, dias = Decimal(0), 0
    dia = desde
    while dia <= hasta:
        h = por_dia[dia.weekday()]
        if h > 0 and dia not in inactivos:
            horas += h
            dias += 1
        dia += timedelta(days=1)
    return horas.quantize(Decimal("0.01")), dias


def presupuesto_calculado(config: ConfiguracionLaboral, proyecto: Proyecto) -> Decimal | None:
    if proyecto.fecha_inicio is None or proyecto.fecha_fin is None or proyecto.fecha_fin < proyecto.fecha_inicio:
        return None
    return horas_laborales(config, proyecto.fecha_inicio, proyecto.fecha_fin)[0]


async def aplicar_presupuesto(db: AsyncSession, proyecto: Proyecto) -> None:
    """Recalcula el presupuesto de un proyecto en modo automático (no confirma)."""
    if not proyecto.horas_presupuestadas_manual:
        proyecto.horas_presupuestadas = presupuesto_calculado(await obtener(db), proyecto)


async def guardar(db: AsyncSession, actor: Actor, data: ConfiguracionLaboralIn) -> ConfiguracionGuardada:
    exigir(actor.es_admin, "Solo el Administrador puede modificar la configuración")
    config = await obtener(db)
    config.horas_entre_semana = data.horas_entre_semana
    config.horas_sabado = data.horas_sabado
    config.dias_inactivos = data.dias_inactivos

    proyectos = await db.scalars(
        select(Proyecto).where(
            Proyecto.horas_presupuestadas_manual.is_(False),
            Proyecto.es_conjunto.is_(False),
            Proyecto.estado_proyecto.not_in([e.value for e in ESTADOS_FINALES]),
        )
    )
    recalculados = excedidos = 0
    for p in proyectos:
        nuevo = presupuesto_calculado(config, p)
        if nuevo == p.horas_presupuestadas:
            continue
        p.horas_presupuestadas = nuevo
        recalculados += 1
        if nuevo is not None:
            usadas = await db.scalar(
                select(func.coalesce(func.sum(Tarea.horas_asignadas), 0)).where(Tarea.id_proyecto == p.id_proyecto)
            )
            excedidos += usadas > nuevo

    for conjunto in await db.scalars(select(Proyecto).where(Proyecto.es_conjunto.is_(True))):
        await conjunto_service.consolidar(db, conjunto)
    await db.commit()
    return ConfiguracionGuardada(
        **ConfiguracionLaboralRead.model_validate(config).model_dump(),
        proyectos_recalculados=recalculados, proyectos_excedidos=excedidos,
    )
