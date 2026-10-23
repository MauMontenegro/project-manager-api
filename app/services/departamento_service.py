"""Configuración de cada departamento: plantilla de etapas y catálogo de etiquetas.
La edita el Gerente del departamento o el Administrador."""
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import Actor, exigir
from app.models.ciclo_vida import MACRO_ETAPAS, normalizar_estados
from app.models.departamento import Etiqueta, PlantillaEtapa
from app.models.enums import DepartamentoProyecto
from app.schemas.departamento import EtiquetaIn, PlantillaEtapasIn


def exigir_gestion(actor: Actor, departamento: str) -> None:
    exigir(
        actor.es_admin or (actor.gestiona_equipo and actor.departamento == departamento),
        f"Solo el Gerente de {departamento} o el Administrador pueden modificar su configuración",
    )


# ---------- Etapas ----------
async def plantilla(db: AsyncSession, departamento: DepartamentoProyecto) -> list[PlantillaEtapa]:
    """Etapas del departamento en orden; si no hay (base nueva), se crean las macro-etapas por defecto."""
    etapas = list(await db.scalars(
        select(PlantillaEtapa).where(PlantillaEtapa.departamento == departamento.value).order_by(PlantillaEtapa.orden)
    ))
    if not etapas:
        etapas = [
            PlantillaEtapa(
                departamento=departamento.value, orden=m.orden, nombre=m.nombre.value, descripcion=m.descripcion,
                estados_permitidos=[e.value for e in m.estados],
            )
            for m in MACRO_ETAPAS
        ]
        db.add_all(etapas)
        await db.flush()
    return etapas


async def guardar_plantilla(
    db: AsyncSession, actor: Actor, departamento: DepartamentoProyecto, data: PlantillaEtapasIn
) -> list[PlantillaEtapa]:
    """Reemplaza las etapas del departamento. Solo afecta a los proyectos que se creen después."""
    exigir_gestion(actor, departamento.value)
    await db.execute(delete(PlantillaEtapa).where(PlantillaEtapa.departamento == departamento.value))
    total = len(data.etapas)
    db.add_all(
        PlantillaEtapa(
            departamento=departamento.value, orden=i, nombre=e.nombre, descripcion=e.descripcion or None,
            estados_permitidos=normalizar_estados(e.estados_permitidos, i, total),
        )
        for i, e in enumerate(data.etapas, start=1)
    )
    await db.commit()
    return await plantilla(db, departamento)


# ---------- Etiquetas ----------
async def listar_etiquetas(db: AsyncSession, departamento: DepartamentoProyecto | None = None) -> list[Etiqueta]:
    stmt = select(Etiqueta).order_by(Etiqueta.departamento, func.lower(Etiqueta.nombre))
    if departamento is not None:
        stmt = stmt.where(Etiqueta.departamento == departamento.value)
    return list(await db.scalars(stmt))


async def _nombre_libre(db: AsyncSession, departamento: str, nombre: str, excepto: int | None = None) -> None:
    stmt = select(Etiqueta.id_etiqueta).where(
        Etiqueta.departamento == departamento, func.lower(Etiqueta.nombre) == nombre.lower()
    )
    if excepto is not None:
        stmt = stmt.where(Etiqueta.id_etiqueta != excepto)
    if await db.scalar(stmt) is not None:
        raise ConflictError(f"Ya existe la etiqueta «{nombre}» en {departamento}")


async def crear_etiqueta(db: AsyncSession, actor: Actor, departamento: DepartamentoProyecto, data: EtiquetaIn) -> Etiqueta:
    exigir_gestion(actor, departamento.value)
    await _nombre_libre(db, departamento.value, data.nombre)
    etiqueta = Etiqueta(departamento=departamento.value, nombre=data.nombre, color=data.color.lower())
    db.add(etiqueta)
    await db.commit()
    return etiqueta


async def _obtener_etiqueta(db: AsyncSession, id_etiqueta: int) -> Etiqueta:
    etiqueta = await db.get(Etiqueta, id_etiqueta)
    if etiqueta is None:
        raise NotFoundError(f"Etiqueta con id {id_etiqueta} no existe")
    return etiqueta


async def actualizar_etiqueta(db: AsyncSession, actor: Actor, id_etiqueta: int, data: EtiquetaIn) -> Etiqueta:
    etiqueta = await _obtener_etiqueta(db, id_etiqueta)
    exigir_gestion(actor, etiqueta.departamento)
    await _nombre_libre(db, etiqueta.departamento, data.nombre, excepto=id_etiqueta)
    etiqueta.nombre, etiqueta.color = data.nombre, data.color.lower()
    await db.commit()
    return etiqueta


async def eliminar_etiqueta(db: AsyncSession, actor: Actor, id_etiqueta: int) -> None:
    """Se quita también de los proyectos que la tenían."""
    etiqueta = await _obtener_etiqueta(db, id_etiqueta)
    exigir_gestion(actor, etiqueta.departamento)
    await db.delete(etiqueta)
    await db.commit()
