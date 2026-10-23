from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import Actor, exigir
from app.models.demanda import SolicitudDemanda
from app.models.organizacion import Area, Empresa
from app.models.seguimiento import CompromisoCliente
from app.models.tablas_uniones import ProyectoEmpresaImpactada
from app.schemas.organizacion import AreaCreate, EmpresaCreate, EmpresaNoEliminada, EmpresasEliminadas
from app.services import auditoria_service


async def crear_empresa(db: AsyncSession, data: EmpresaCreate) -> Empresa:
    if await db.scalar(select(Empresa.id_empresa).where(Empresa.nombre_empresa == data.nombre_empresa)):
        raise ConflictError(f"Ya existe la empresa '{data.nombre_empresa}'")
    empresa = Empresa(**data.model_dump())
    db.add(empresa)
    await db.commit()
    await db.refresh(empresa)
    return empresa


async def listar_empresas(db: AsyncSession) -> list[Empresa]:
    return list(await db.scalars(select(Empresa).order_by(Empresa.nombre_empresa)))


async def crear_area(db: AsyncSession, data: AreaCreate) -> Area:
    if await db.get(Empresa, data.id_empresa) is None:
        raise NotFoundError(f"Empresa con id {data.id_empresa} no existe")
    if await db.scalar(select(Area.id_area).where(Area.codigo_area == data.codigo_area)):
        raise ConflictError(f"Ya existe un área con código '{data.codigo_area}'")
    area = Area(**data.model_dump())
    db.add(area)
    await db.commit()
    await db.refresh(area)
    return area


async def listar_areas(db: AsyncSession, id_empresa: int | None = None) -> list[Area]:
    stmt = select(Area).order_by(Area.nombre_area)
    if id_empresa is not None:
        stmt = stmt.where(Area.id_empresa == id_empresa)
    return list(await db.scalars(stmt))


async def _conteo(db: AsyncSession, columna, ids: list[int]) -> dict[int, int]:
    filas = await db.execute(select(columna, func.count()).where(columna.in_(ids)).group_by(columna))
    return dict(filas.all())


async def _motivos_en_uso(db: AsyncSession, ids: list[int]) -> dict[int, str]:
    """Por qué no se puede eliminar cada empresa: sigue referida por proyectos, demanda o compromisos.
    Sus áreas se eliminan con ella solo si ninguna está en uso."""
    area_empresa = dict((await db.execute(select(Area.id_area, Area.id_empresa).where(Area.id_empresa.in_(ids)))).all())
    usos: dict[int, list[str]] = {}

    def sumar(conteo: dict[int, int], singular: str, plural: str, por_area: bool = False) -> None:
        total: dict[int, int] = {}
        for clave, n in conteo.items():
            empresa = area_empresa[clave] if por_area else clave
            total[empresa] = total.get(empresa, 0) + n
        for empresa, n in total.items():
            usos.setdefault(empresa, []).append(f"{n} {singular if n == 1 else plural}")

    sumar(await _conteo(db, ProyectoEmpresaImpactada.id_empresa, ids), "proyecto la tiene como impactada", "proyectos la tienen como impactada")
    sumar(await _conteo(db, SolicitudDemanda.id_empresa, ids), "solicitud de demanda", "solicitudes de demanda")
    if area_empresa:
        areas = list(area_empresa)
        sumar(await _conteo(db, SolicitudDemanda.id_area, areas), "solicitud usa sus áreas", "solicitudes usan sus áreas", True)
        sumar(await _conteo(db, CompromisoCliente.id_area_cliente, areas), "compromiso de cliente usa sus áreas", "compromisos de cliente usan sus áreas", True)
    return {empresa: "En uso: " + ", ".join(lista) for empresa, lista in usos.items()}


async def eliminar_empresas(db: AsyncSession, actor: Actor, ids: list[int]) -> EmpresasEliminadas:
    """Elimina las empresas (y sus áreas) que no están en uso. Solo el Administrador."""
    exigir(actor.es_admin, "Solo el Administrador puede eliminar empresas")
    ids = list(dict.fromkeys(ids))
    empresas = {e.id_empresa: e for e in await db.scalars(select(Empresa).where(Empresa.id_empresa.in_(ids)))}
    motivos = await _motivos_en_uso(db, list(empresas))
    no_eliminadas = [EmpresaNoEliminada(id_empresa=i, nombre_empresa=None, motivo="No existe") for i in ids if i not in empresas]
    eliminadas = []
    for i, empresa in empresas.items():
        if i in motivos:
            no_eliminadas.append(EmpresaNoEliminada(id_empresa=i, nombre_empresa=empresa.nombre_empresa, motivo=motivos[i]))
            continue
        auditoria_service.registrar(
            db, actor, entidad="empresa", id_entidad=i, accion="baja", resumen=f"Eliminó la empresa «{empresa.nombre_empresa}»",
        )
        eliminadas.append(i)
    if eliminadas:
        await db.execute(delete(Area).where(Area.id_empresa.in_(eliminadas)))
        await db.execute(delete(Empresa).where(Empresa.id_empresa.in_(eliminadas)))
    await db.commit()
    return EmpresasEliminadas(eliminadas=eliminadas, no_eliminadas=no_eliminadas)


async def eliminar_empresa(db: AsyncSession, actor: Actor, id_empresa: int) -> None:
    resultado = await eliminar_empresas(db, actor, [id_empresa])
    if resultado.no_eliminadas:
        motivo = resultado.no_eliminadas[0]
        if motivo.nombre_empresa is None:
            raise NotFoundError(f"Empresa con id {id_empresa} no existe")
        raise ConflictError(f"No se puede eliminar «{motivo.nombre_empresa}». {motivo.motivo}")
