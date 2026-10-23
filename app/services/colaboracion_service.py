"""Comentarios con @menciones en las tareas, su línea de tiempo y las notificaciones de mención.

Pueden comentar y ser mencionadas las personas del proyecto (su líder y quienes tienen una
asignación; en un proyecto conjunto, las de él y todos sus subproyectos) o, en una tarea recurrente, su responsable y los Gerentes de su departamento; Gerentes y
Administrador también pueden comentar. Cada mención es una notificación para
la persona mencionada hasta que la marca como leída.
"""
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.security import Actor, exigir
from app.models.equipo import Bitacora
from app.models.operacion import ComentarioTarea, Mencion, Tarea
from app.models.organizacion import Usuario
from app.models.proyecto import Proyecto
from app.models.tablas_uniones import AsignacionRecurso
from app.services import conjunto_service, recurrente_service
from app.schemas.colaboracion import (
    ComentarioCreate, EventoTarea, Involucrado, Notificacion, Notificaciones, PersonaMencionada,
)


async def involucrados(db: AsyncSession, id_proyecto: int) -> list[Involucrado]:
    """Líder y asignados del proyecto. En un conjunto o un subproyecto, los de todo el conjunto: sus tareas
    se encadenan entre departamentos."""
    proyecto = await db.get(Proyecto, id_proyecto)
    if proyecto is None:
        raise NotFoundError(f"Proyecto con id {id_proyecto} no existe")
    familia = await conjunto_service.ids_familia(db, proyecto)
    asignados = select(AsignacionRecurso.id_usuario).where(AsignacionRecurso.id_proyecto.in_(familia))
    lideres = select(Proyecto.lider_id).where(Proyecto.id_proyecto.in_(familia))
    personas = await db.scalars(
        select(Usuario)
        .where(Usuario.activo.is_(True), Usuario.id_usuario.in_(lideres) | Usuario.id_usuario.in_(asignados))
        .order_by(Usuario.nombre)
    )
    return [Involucrado(id_usuario=u.id_usuario, nombre=u.nombre, es_lider=u.id_usuario == proyecto.lider_id) for u in personas]


async def involucrados_de_tarea(db: AsyncSession, id_tarea: int) -> list[Involucrado]:
    """Quiénes pueden comentar y ser mencionados en la tarea, sea de proyecto o recurrente."""
    tarea = await _tarea(db, id_tarea)
    if tarea.id_proyecto is not None:
        return await involucrados(db, tarea.id_proyecto)
    return [
        Involucrado(id_usuario=u.id_usuario, nombre=u.nombre, es_lider=u.id_usuario == tarea.id_usuario)
        for u in await recurrente_service.involucrados(db, tarea)
    ]


async def _tarea(db: AsyncSession, id_tarea: int) -> Tarea:
    tarea = await db.get(Tarea, id_tarea)
    if tarea is None:
        raise NotFoundError(f"Tarea con id {id_tarea} no existe")
    return tarea


async def comentar(db: AsyncSession, actor: Actor, id_tarea: int, data: ComentarioCreate) -> EventoTarea:
    personas = {p.id_usuario: p.nombre for p in await involucrados_de_tarea(db, id_tarea)}
    exigir(
        actor.gestiona_equipo or actor.id_usuario in personas,
        "Solo las personas de la tarea, los Gerentes o el Administrador pueden comentar",
    )
    texto = data.texto.strip()
    if not texto:
        raise BusinessRuleError("El comentario está vacío")
    ajenos = set(data.menciones) - personas.keys()
    if ajenos:
        raise BusinessRuleError(f"Solo puedes mencionar a personas de la tarea (ids no válidos: {sorted(ajenos)})")

    comentario = ComentarioTarea(id_tarea=id_tarea, id_autor=actor.id_usuario, autor_nombre=actor.nombre, texto=texto)
    # Mencionarse a sí mismo no genera notificación.
    comentario.menciones = [Mencion(id_usuario=i) for i in dict.fromkeys(data.menciones) if i != actor.id_usuario]
    db.add(comentario)
    await db.commit()
    comentario = await db.scalar(
        select(ComentarioTarea)
        .where(ComentarioTarea.id_comentario == comentario.id_comentario)
        .options(selectinload(ComentarioTarea.menciones))
        .execution_options(populate_existing=True)
    )
    return _evento_comentario(comentario, personas)


async def eliminar_comentario(db: AsyncSession, actor: Actor, id_comentario: int) -> None:
    comentario = await db.get(ComentarioTarea, id_comentario)
    if comentario is None:
        raise NotFoundError(f"Comentario con id {id_comentario} no existe")
    exigir(
        actor.gestiona_equipo or (actor.id_usuario is not None and actor.id_usuario == comentario.id_autor),
        "Solo el autor, los Gerentes o el Administrador pueden borrar un comentario",
    )
    await db.delete(comentario)
    await db.commit()


def _evento_comentario(c: ComentarioTarea, nombres: dict[int, str]) -> EventoTarea:
    return EventoTarea(
        tipo="comentario", fecha=c.fecha, id_actor=c.id_autor, actor_nombre=c.autor_nombre,
        id_comentario=c.id_comentario, texto=c.texto,
        menciones=[PersonaMencionada(id_usuario=m.id_usuario, nombre=nombres.get(m.id_usuario, f"#{m.id_usuario}")) for m in c.menciones],
    )


async def actividad(db: AsyncSession, id_tarea: int) -> list[EventoTarea]:
    """Cambios y comentarios de la tarea, del más antiguo al más reciente."""
    tarea = await _tarea(db, id_tarea)
    cambios = await db.scalars(
        select(Bitacora).where(Bitacora.entidad == "tarea", Bitacora.id_entidad == id_tarea)
    )
    comentarios = list(await db.scalars(
        select(ComentarioTarea).where(ComentarioTarea.id_tarea == tarea.id_tarea).options(selectinload(ComentarioTarea.menciones))
    ))
    ids = {m.id_usuario for c in comentarios for m in c.menciones}
    nombres = dict((await db.execute(select(Usuario.id_usuario, Usuario.nombre).where(Usuario.id_usuario.in_(ids)))).all()) if ids else {}

    eventos = [
        EventoTarea(tipo="cambio", fecha=b.fecha, id_actor=b.id_actor, actor_nombre=b.actor_nombre,
                    accion=b.accion, resumen=b.resumen, cambios=b.cambios)
        for b in cambios
    ] + [_evento_comentario(c, nombres) for c in comentarios]
    return sorted(eventos, key=lambda e: e.fecha)


async def conteo_comentarios(db: AsyncSession, ids_tareas: list[int]) -> dict[int, int]:
    if not ids_tareas:
        return {}
    filas = await db.execute(
        select(ComentarioTarea.id_tarea, func.count()).where(ComentarioTarea.id_tarea.in_(ids_tareas)).group_by(ComentarioTarea.id_tarea)
    )
    return dict(filas.all())


# ---------- Notificaciones (menciones) ----------
async def notificaciones(db: AsyncSession, actor: Actor, *, solo_no_leidas: bool = False, limit: int = 30) -> Notificaciones:
    if actor.id_usuario is None:
        return Notificaciones(no_leidas=0, items=[])
    no_leidas = await db.scalar(
        select(func.count()).where(Mencion.id_usuario == actor.id_usuario, Mencion.leida.is_(False))
    )
    stmt = (
        select(Mencion, ComentarioTarea, Tarea, Proyecto)
        .join(ComentarioTarea, ComentarioTarea.id_comentario == Mencion.id_comentario)
        .join(Tarea, Tarea.id_tarea == ComentarioTarea.id_tarea)
        .outerjoin(Proyecto, Proyecto.id_proyecto == Tarea.id_proyecto)
        .where(Mencion.id_usuario == actor.id_usuario)
        .order_by(ComentarioTarea.fecha.desc())
        .limit(limit)
    )
    if solo_no_leidas:
        stmt = stmt.where(Mencion.leida.is_(False))
    items = [
        Notificacion(
            id_mencion=m.id_mencion, leida=m.leida, fecha=c.fecha, autor_nombre=c.autor_nombre, texto=c.texto,
            id_tarea=t.id_tarea, titulo_tarea=t.titulo, id_proyecto=p.id_proyecto if p else None,
            nombre_proyecto=p.nombre_proyecto if p else None, id_recurrente=t.id_recurrente,
        )
        for m, c, t, p in await db.execute(stmt)
    ]
    return Notificaciones(no_leidas=no_leidas or 0, items=items)


async def marcar_leidas(db: AsyncSession, actor: Actor, id_mencion: int | None = None) -> None:
    """Marca una mención (o todas, sin `id_mencion`) de quien consulta como leída."""
    if actor.id_usuario is None:
        return
    stmt = update(Mencion).where(Mencion.id_usuario == actor.id_usuario, Mencion.leida.is_(False))
    if id_mencion is not None:
        mencion = await db.get(Mencion, id_mencion)
        if mencion is None or mencion.id_usuario != actor.id_usuario:
            raise NotFoundError(f"Notificación con id {id_mencion} no existe")
        stmt = stmt.where(Mencion.id_mencion == id_mencion)
    await db.execute(stmt.values(leida=True, fecha_leida=datetime.now(UTC)))
    await db.commit()
