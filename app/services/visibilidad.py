"""Qué proyectos (y, con ellos, sus tareas, etapas, asignaciones y bloqueos) puede *consultar* cada rol.
Modificar sigue sus propias reglas (`Actor.gestiona_*`); esto solo acota la lectura.

- Administrador: todos.
- Gerente y Líder: los de su departamento (el Gerente, también los que aún no tienen departamento).
- Cualquiera: los que lidera, en los que está asignado o tiene alguna tarea.

Un proyecto conjunto se ve entero: si alguien ve una parte (el conjunto o uno de sus subproyectos), ve el conjunto y
todos sus subproyectos, porque sus tareas se entrelazan (dependencias cruzadas y vista general).

Lo que no se puede ver responde `404`, igual que si no existiera, para no revelar qué proyectos hay.
"""
from sqlalchemy import ColumnElement, and_, exists, false, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import NotFoundError
from app.core.security import Actor
from app.models.enums import RolSistema
from app.models.operacion import Tarea
from app.models.organizacion import Usuario
from app.models.proyecto import Proyecto
from app.models.tablas_uniones import AsignacionRecurso
from app.services import recurrente_service


def _participa(actor: Actor, p) -> ColumnElement[bool]:
    """`p` (Proyecto o un alias) es visible por sí mismo, sin contar a su familia."""
    condiciones = []
    if actor.id_usuario is not None:
        yo = actor.id_usuario
        condiciones += [
            p.lider_id == yo,
            exists().where(AsignacionRecurso.id_proyecto == p.id_proyecto, AsignacionRecurso.id_usuario == yo),
            exists().where(Tarea.id_proyecto == p.id_proyecto, Tarea.id_usuario == yo),
        ]
    if actor.rol in (RolSistema.GERENTE, RolSistema.LIDER) and actor.departamento is not None:
        condiciones.append(p.departamento == actor.departamento.value)
    if actor.rol == RolSistema.GERENTE:
        condiciones.append(and_(p.departamento.is_(None), not_(p.es_conjunto)))
    return or_(*condiciones) if condiciones else false()


def condicion(actor: Actor, p=Proyecto) -> ColumnElement[bool] | None:
    """Filtro sobre `p` con los proyectos visibles; `None` si el actor ve todos."""
    if actor.es_admin:
        return None
    familia = aliased(Proyecto)
    raiz = lambda x: func.coalesce(x.id_proyecto_padre, x.id_proyecto)  # noqa: E731
    return exists().where(raiz(familia) == raiz(p), _participa(actor, familia))


async def ids_visibles(db: AsyncSession, actor: Actor) -> list[int] | None:
    """Ids de los proyectos visibles (subproyectos incluidos); `None` si el actor ve todos."""
    cond = condicion(actor)
    return None if cond is None else list(await db.scalars(select(Proyecto.id_proyecto).where(cond)))


async def puede_ver(db: AsyncSession, actor: Actor, id_proyecto: int) -> bool:
    cond = condicion(actor)
    if cond is None:
        return True
    return bool(await db.scalar(select(exists().where(Proyecto.id_proyecto == id_proyecto, cond))))


async def exigir_proyecto(db: AsyncSession, actor: Actor, id_proyecto: int) -> None:
    if not await puede_ver(db, actor, id_proyecto):
        raise NotFoundError(f"Proyecto con id {id_proyecto} no existe")


async def exigir_tarea(db: AsyncSession, actor: Actor, id_tarea: int) -> Tarea:
    """La tarea de un proyecto, si su proyecto es visible. Las recurrentes, la persona, quien gestiona su
    departamento o el Administrador."""
    tarea = await db.get(Tarea, id_tarea)
    if tarea is None:
        raise NotFoundError(f"Tarea con id {id_tarea} no existe")
    if tarea.id_proyecto is None:
        if not (actor.es_admin or recurrente_service.gestiona_persona(actor, await db.get(Usuario, tarea.id_usuario))):
            raise NotFoundError(f"Tarea con id {id_tarea} no existe")
    elif not await puede_ver(db, actor, tarea.id_proyecto):
        raise NotFoundError(f"Tarea con id {id_tarea} no existe")
    return tarea
