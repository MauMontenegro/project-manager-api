"""Bitácora de cambios. Las entradas se agregan a la sesión de la operación auditada,
así se confirman (o se descartan) en la misma transacción."""
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Actor
from app.models.equipo import Bitacora


def _json(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return format(valor.normalize(), "f")
    if isinstance(valor, date):
        return valor.isoformat()
    return valor


def diferencias(antes: dict[str, Any], despues: dict[str, Any]) -> dict[str, list[Any]]:
    """{campo: [antes, después]} solo para los campos que cambiaron."""
    return {
        campo: [_json(antes.get(campo)), _json(valor)]
        for campo, valor in despues.items()
        if _json(antes.get(campo)) != _json(valor)
    }


def registrar(
    db: AsyncSession,
    actor: Actor,
    *,
    entidad: str,
    id_entidad: int,
    accion: str,
    resumen: str,
    id_usuario_afectado: int | None = None,
    cambios: dict[str, Any] | None = None,
) -> None:
    db.add(
        Bitacora(
            id_actor=actor.id_usuario,
            actor_nombre=actor.nombre,
            entidad=entidad,
            id_entidad=id_entidad,
            id_usuario_afectado=id_usuario_afectado,
            accion=accion,
            resumen=resumen,
            cambios=cambios or None,
        )
    )


async def listar(
    db: AsyncSession, *, id_usuario_afectado: int | None = None, entidad: str | None = None, limit: int = 50
) -> list[Bitacora]:
    stmt = select(Bitacora).order_by(Bitacora.fecha.desc(), Bitacora.id_bitacora.desc()).limit(limit)
    if id_usuario_afectado is not None:
        stmt = stmt.where(Bitacora.id_usuario_afectado == id_usuario_afectado)
    if entidad is not None:
        stmt = stmt.where(Bitacora.entidad == entidad)
    return list(await db.scalars(stmt))
