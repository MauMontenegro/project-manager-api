from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.enums import CausaRaiz, ResponsableOrigen
from app.models.operacion import BloqueoInterrupcion, EtapaProyecto
from app.models.proyecto import Proyecto
from app.schemas.bloqueo import BloqueoCerrar, BloqueoCreate, BloqueoUpdate

SEGUNDOS_POR_DIA = Decimal(86400)


def calcular_dias_impacto(inicio: datetime, fin: datetime) -> Decimal:
    """Días transcurridos (fraccionales, 2 decimales) entre el inicio y el fin del bloqueo."""
    segundos = Decimal(str((fin - inicio).total_seconds()))
    return (segundos / SEGUNDOS_POR_DIA).quantize(Decimal("0.01"))


async def obtener_bloqueo(db: AsyncSession, id_bloqueo: int) -> BloqueoInterrupcion:
    bloqueo = await db.get(BloqueoInterrupcion, id_bloqueo)
    if bloqueo is None:
        raise NotFoundError(f"Bloqueo con id {id_bloqueo} no existe")
    return bloqueo


async def registrar_bloqueo(db: AsyncSession, data: BloqueoCreate) -> BloqueoInterrupcion:
    if await db.get(Proyecto, data.id_proyecto) is None:
        raise NotFoundError(f"Proyecto con id {data.id_proyecto} no existe")
    etapa = await db.get(EtapaProyecto, data.id_etapa)
    if etapa is None or etapa.id_proyecto != data.id_proyecto:
        raise NotFoundError(f"La etapa {data.id_etapa} no existe en el proyecto {data.id_proyecto}")

    inicio = data.fecha_inicio_bloqueo or datetime.now(timezone.utc)
    bloqueo = BloqueoInterrupcion(
        id_proyecto=data.id_proyecto,
        id_etapa=data.id_etapa,
        causa_raiz=data.causa_raiz.value,
        responsable_origen=data.responsable_origen.value,
        fecha_inicio_bloqueo=inicio,
        fecha_fin_bloqueo=data.fecha_fin_bloqueo,
        dias_impacto=(
            calcular_dias_impacto(inicio, data.fecha_fin_bloqueo) if data.fecha_fin_bloqueo is not None else None
        ),
    )
    db.add(bloqueo)
    await db.commit()
    await db.refresh(bloqueo)
    return bloqueo


async def cerrar_bloqueo(db: AsyncSession, id_bloqueo: int, data: BloqueoCerrar) -> BloqueoInterrupcion:
    bloqueo = await obtener_bloqueo(db, id_bloqueo)
    if bloqueo.fecha_fin_bloqueo is not None:
        raise BusinessRuleError(f"El bloqueo {id_bloqueo} ya fue cerrado")
    return await _aplicar_fin(db, bloqueo, data.fecha_fin_bloqueo or datetime.now(timezone.utc))


async def actualizar_bloqueo(db: AsyncSession, id_bloqueo: int, data: BloqueoUpdate) -> BloqueoInterrupcion:
    bloqueo = await obtener_bloqueo(db, id_bloqueo)
    cambios = data.model_dump(exclude_unset=True)

    for campo in ("causa_raiz", "responsable_origen", "fecha_inicio_bloqueo"):
        if campo in cambios and cambios[campo] is None:
            raise BusinessRuleError(f"{campo} no puede ser nulo")

    for campo, valor in cambios.items():
        setattr(bloqueo, campo, valor.value if isinstance(valor, (CausaRaiz, ResponsableOrigen)) else valor)

    if bloqueo.fecha_fin_bloqueo is not None:
        return await _aplicar_fin(db, bloqueo, bloqueo.fecha_fin_bloqueo)

    bloqueo.dias_impacto = None
    await db.commit()
    await db.refresh(bloqueo)
    return bloqueo


async def _aplicar_fin(db: AsyncSession, bloqueo: BloqueoInterrupcion, fin: datetime) -> BloqueoInterrupcion:
    if fin < bloqueo.fecha_inicio_bloqueo:
        raise BusinessRuleError("fecha_fin_bloqueo no puede ser anterior a fecha_inicio_bloqueo")
    bloqueo.fecha_fin_bloqueo = fin
    bloqueo.dias_impacto = calcular_dias_impacto(bloqueo.fecha_inicio_bloqueo, fin)
    await db.commit()
    await db.refresh(bloqueo)
    return bloqueo


async def listar_bloqueos(
    db: AsyncSession,
    *,
    id_proyecto: int | None = None,
    id_etapa: int | None = None,
    causa_raiz: CausaRaiz | None = None,
    responsable_origen: ResponsableOrigen | None = None,
    abierto: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[BloqueoInterrupcion]:
    stmt = select(BloqueoInterrupcion)
    if id_proyecto is not None:
        stmt = stmt.where(BloqueoInterrupcion.id_proyecto == id_proyecto)
    if id_etapa is not None:
        stmt = stmt.where(BloqueoInterrupcion.id_etapa == id_etapa)
    if causa_raiz is not None:
        stmt = stmt.where(BloqueoInterrupcion.causa_raiz == causa_raiz.value)
    if responsable_origen is not None:
        stmt = stmt.where(BloqueoInterrupcion.responsable_origen == responsable_origen.value)
    if abierto is True:
        stmt = stmt.where(BloqueoInterrupcion.fecha_fin_bloqueo.is_(None))
    elif abierto is False:
        stmt = stmt.where(BloqueoInterrupcion.fecha_fin_bloqueo.is_not(None))

    stmt = stmt.order_by(BloqueoInterrupcion.fecha_inicio_bloqueo.desc()).limit(limit).offset(offset)
    return list(await db.scalars(stmt))


async def eliminar_bloqueo(db: AsyncSession, id_bloqueo: int) -> None:
    bloqueo = await obtener_bloqueo(db, id_bloqueo)
    await db.delete(bloqueo)
    await db.commit()
