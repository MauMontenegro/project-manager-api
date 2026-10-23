"""Equipos de trabajo (workspaces). Los administran los Gerentes y el Administrador; solo organizan personas y
proyectos (no dan permisos). Un proyecto pertenece a uno o a ninguno; un subproyecto, al de su conjunto."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import Actor, exigir
from app.models.ciclo_vida import ESTADOS_FINALES
from app.models.enums import Semaforo
from app.models.equipo_trabajo import EquipoTrabajo
from app.models.operacion import BloqueoInterrupcion
from app.models.organizacion import Usuario
from app.models.proyecto import Proyecto
from app.schemas.equipo_trabajo import EquipoTrabajoIn, EquipoTrabajoRead, EquipoTrabajoUpdate, MiembroRead
from app.services import auditoria_service

MSG_GESTION = "Solo los Gerentes o el Administrador pueden administrar los equipos de trabajo"
CERRADOS = [e.value for e in ESTADOS_FINALES]


async def _leer(db: AsyncSession, equipos: list[EquipoTrabajo]) -> list[EquipoTrabajoRead]:
    ids = [e.id_equipo_trabajo for e in equipos]
    abierto = Proyecto.estado_proyecto.not_in(CERRADOS)
    conteos = {
        i: (total, abiertos, riesgo)
        for i, total, abiertos, riesgo in await db.execute(
            select(
                Proyecto.id_equipo_trabajo, func.count(),
                func.count().filter(abierto),
                func.count().filter(abierto, Proyecto.semaforo != Semaforo.VERDE.value),
            )
            .where(Proyecto.id_equipo_trabajo.in_(ids), Proyecto.id_proyecto_padre.is_(None))
            .group_by(Proyecto.id_equipo_trabajo)
        )
    } if ids else {}
    bloqueos = dict((await db.execute(
        select(Proyecto.id_equipo_trabajo, func.count())
        .join(BloqueoInterrupcion, BloqueoInterrupcion.id_proyecto == Proyecto.id_proyecto)
        .where(Proyecto.id_equipo_trabajo.in_(ids), BloqueoInterrupcion.fecha_fin_bloqueo.is_(None))
        .group_by(Proyecto.id_equipo_trabajo)
    )).all()) if ids else {}
    return [
        EquipoTrabajoRead(
            id_equipo_trabajo=e.id_equipo_trabajo, nombre=e.nombre, descripcion=e.descripcion, color=e.color,
            fecha_creacion=e.fecha_creacion,
            miembros=[MiembroRead(id_usuario=u.id_usuario, nombre=u.nombre, departamento=u.departamento) for u in e.miembros],
            proyectos=conteos.get(e.id_equipo_trabajo, (0, 0, 0))[0], proyectos_abiertos=conteos.get(e.id_equipo_trabajo, (0, 0, 0))[1],
            proyectos_en_riesgo=conteos.get(e.id_equipo_trabajo, (0, 0, 0))[2], bloqueos_abiertos=bloqueos.get(e.id_equipo_trabajo, 0),
        )
        for e in equipos
    ]


def _consulta():
    return select(EquipoTrabajo).options(selectinload(EquipoTrabajo.miembros)).order_by(func.lower(EquipoTrabajo.nombre))


async def listar(db: AsyncSession, *, id_usuario: int | None = None) -> list[EquipoTrabajoRead]:
    """Todos o, con `id_usuario`, aquellos en que participa esa persona."""
    stmt = _consulta()
    if id_usuario is not None:
        stmt = stmt.where(EquipoTrabajo.miembros.any(Usuario.id_usuario == id_usuario))
    return await _leer(db, list(await db.scalars(stmt)))


async def _obtener(db: AsyncSession, id_equipo: int) -> EquipoTrabajo:
    equipo = await db.scalar(
        _consulta().where(EquipoTrabajo.id_equipo_trabajo == id_equipo).execution_options(populate_existing=True)
    )
    if equipo is None:
        raise NotFoundError(f"Equipo de trabajo con id {id_equipo} no existe")
    return equipo


async def obtener(db: AsyncSession, id_equipo: int) -> EquipoTrabajoRead:
    return (await _leer(db, [await _obtener(db, id_equipo)]))[0]


async def existe(db: AsyncSession, id_equipo: int) -> None:
    if await db.get(EquipoTrabajo, id_equipo) is None:
        raise NotFoundError(f"Equipo de trabajo con id {id_equipo} no existe")


async def _nombre_libre(db: AsyncSession, nombre: str, excepto: int | None = None) -> None:
    stmt = select(EquipoTrabajo.id_equipo_trabajo).where(func.lower(EquipoTrabajo.nombre) == nombre.lower())
    if excepto is not None:
        stmt = stmt.where(EquipoTrabajo.id_equipo_trabajo != excepto)
    if await db.scalar(stmt) is not None:
        raise ConflictError(f"Ya existe el equipo de trabajo «{nombre}»")


async def _personas(db: AsyncSession, ids: list[int]) -> list[Usuario]:
    ids = list(dict.fromkeys(ids))
    personas = list(await db.scalars(select(Usuario).where(Usuario.id_usuario.in_(ids)))) if ids else []
    faltan = set(ids) - {u.id_usuario for u in personas}
    if faltan:
        raise NotFoundError(f"Personas inexistentes: {sorted(faltan)}")
    return personas


async def crear(db: AsyncSession, actor: Actor, data: EquipoTrabajoIn) -> EquipoTrabajoRead:
    exigir(actor.gestiona_equipo, MSG_GESTION)
    nombre = data.nombre.strip()
    await _nombre_libre(db, nombre)
    equipo = EquipoTrabajo(nombre=nombre, descripcion=(data.descripcion or "").strip() or None, color=data.color.lower())
    equipo.miembros = await _personas(db, data.miembros)
    db.add(equipo)
    await db.flush()
    auditoria_service.registrar(
        db, actor, entidad="equipo_trabajo", id_entidad=equipo.id_equipo_trabajo, accion="alta",
        resumen=f"Creó el equipo de trabajo «{nombre}» con {len(equipo.miembros)} persona(s)",
    )
    await db.commit()
    return await obtener(db, equipo.id_equipo_trabajo)


async def actualizar(db: AsyncSession, actor: Actor, id_equipo: int, data: EquipoTrabajoUpdate) -> EquipoTrabajoRead:
    exigir(actor.gestiona_equipo, MSG_GESTION)
    equipo = await _obtener(db, id_equipo)
    cambios = data.model_dump(exclude_unset=True)
    partes = []
    if cambios.get("nombre") is not None and cambios["nombre"].strip() != equipo.nombre:
        nombre = cambios["nombre"].strip()
        await _nombre_libre(db, nombre, excepto=id_equipo)
        partes.append(f"Nombre: «{equipo.nombre}» → «{nombre}»")
        equipo.nombre = nombre
    if "descripcion" in cambios:
        equipo.descripcion = (cambios["descripcion"] or "").strip() or None
    if cambios.get("color"):
        equipo.color = cambios["color"].lower()
    if cambios.get("miembros") is not None:
        antes = {u.id_usuario: u.nombre for u in equipo.miembros}
        equipo.miembros = await _personas(db, cambios["miembros"])
        despues = {u.id_usuario: u.nombre for u in equipo.miembros}
        if entran := [n for i, n in despues.items() if i not in antes]:
            partes.append(f"Se suman: {', '.join(entran)}")
        if salen := [n for i, n in antes.items() if i not in despues]:
            partes.append(f"Salen: {', '.join(salen)}")
    auditoria_service.registrar(
        db, actor, entidad="equipo_trabajo", id_entidad=id_equipo, accion="edicion",
        resumen=f"Editó el equipo de trabajo «{equipo.nombre}»" + (f" · {'; '.join(partes)}" if partes else ""),
    )
    await db.commit()
    return await obtener(db, id_equipo)


async def eliminar(db: AsyncSession, actor: Actor, id_equipo: int) -> None:
    """Sus proyectos quedan sin equipo de trabajo; las personas no se tocan."""
    exigir(actor.gestiona_equipo, MSG_GESTION)
    equipo = await _obtener(db, id_equipo)
    auditoria_service.registrar(
        db, actor, entidad="equipo_trabajo", id_entidad=id_equipo, accion="baja",
        resumen=f"Eliminó el equipo de trabajo «{equipo.nombre}»",
    )
    await db.delete(equipo)
    await db.commit()
