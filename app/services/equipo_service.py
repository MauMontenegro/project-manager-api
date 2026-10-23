"""Catálogos del Equipo (puestos, skills), ausencias y asignaciones por persona."""
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import Actor, exigir
from app.models.enums import EstadoEtapa, EstadoProyecto
from app.models.equipo import Ausencia, Skill, UsuarioSkill
from app.models.operacion import EtapaProyecto, Tarea
from app.models.organizacion import Puesto, Usuario
from app.models.proyecto import Proyecto
from app.models.tablas_uniones import AsignacionRecurso
from app.schemas.equipo import AsignacionPersonaRead, AusenciaCreate, SkillCatalogoRead
from app.schemas.usuario import PuestoCreate
from app.services import auditoria_service, visibilidad
from app.services.usuario_service import obtener_usuario

# Proyectos que no consumen capacidad: completados, cancelados o en pausa.
ESTADOS_PROYECTO_SIN_CARGA = {
    EstadoProyecto.COMPLETADO.value, EstadoProyecto.CANCELADO.value, EstadoProyecto.PAUSADO.value,
}
# Etapas que ya no consumen capacidad.
ESTADOS_ETAPA_SIN_CARGA = {EstadoEtapa.COMPLETADO.value, EstadoEtapa.CANCELADO.value}

MSG_CATALOGO = "Solo el Administrador y los Gerentes pueden modificar los catálogos"


# ---------- Puestos ----------
async def listar_puestos(db: AsyncSession) -> list[Puesto]:
    return list(await db.scalars(select(Puesto).order_by(Puesto.nombre_puesto)))


async def crear_puesto(db: AsyncSession, actor: Actor, data: PuestoCreate) -> Puesto:
    exigir(actor.gestiona_equipo, MSG_CATALOGO)
    existente = select(Puesto.id_puesto).where(func.lower(Puesto.nombre_puesto) == data.nombre_puesto.lower())
    if await db.scalar(existente):
        raise ConflictError(f"Ya existe el puesto '{data.nombre_puesto}'")
    puesto = Puesto(**data.model_dump())
    db.add(puesto)
    await db.flush()
    auditoria_service.registrar(
        db, actor, entidad="puesto", id_entidad=puesto.id_puesto, accion="alta", resumen=f"Puesto «{puesto.nombre_puesto}» creado"
    )
    await db.commit()
    return puesto


async def eliminar_puesto(db: AsyncSession, actor: Actor, id_puesto: int) -> None:
    exigir(actor.gestiona_equipo, MSG_CATALOGO)
    puesto = await db.get(Puesto, id_puesto)
    if puesto is None:
        raise NotFoundError(f"Puesto con id {id_puesto} no existe")
    en_uso = await db.scalar(select(func.count()).select_from(Usuario).where(Usuario.id_puesto == id_puesto))
    if en_uso:
        raise ConflictError(
            f"No se puede eliminar '{puesto.nombre_puesto}': lo tienen {en_uso} persona(s). Reasígnalas primero."
        )
    auditoria_service.registrar(
        db, actor, entidad="puesto", id_entidad=id_puesto, accion="baja", resumen=f"Puesto «{puesto.nombre_puesto}» eliminado"
    )
    await db.delete(puesto)
    await db.commit()


# ---------- Catálogo de skills ----------
async def listar_skills(db: AsyncSession) -> list[SkillCatalogoRead]:
    personas = func.count(UsuarioSkill.id_usuario)
    filas = await db.execute(
        select(Skill.id_skill, Skill.nombre, personas)
        .outerjoin(UsuarioSkill, UsuarioSkill.id_skill == Skill.id_skill)
        .group_by(Skill.id_skill)
        .order_by(func.lower(Skill.nombre))
    )
    return [SkillCatalogoRead(id_skill=i, nombre=n, personas=c) for i, n, c in filas]


async def _skill(db: AsyncSession, id_skill: int) -> Skill:
    skill = await db.get(Skill, id_skill)
    if skill is None:
        raise NotFoundError(f"Skill con id {id_skill} no existe")
    return skill


async def renombrar_skill(db: AsyncSession, actor: Actor, id_skill: int, nombre: str) -> None:
    exigir(actor.gestiona_equipo, MSG_CATALOGO)
    skill = await _skill(db, id_skill)
    otro = await db.scalar(select(Skill.id_skill).where(func.lower(Skill.nombre) == nombre.lower(), Skill.id_skill != id_skill))
    if otro is not None:
        raise ConflictError(f"Ya existe el skill '{nombre}'. Usa «Fusionar» para unificarlos.")
    auditoria_service.registrar(
        db, actor, entidad="skill", id_entidad=id_skill, accion="edicion",
        resumen=f"Skill «{skill.nombre}» renombrado a «{nombre}»",
    )
    skill.nombre = nombre
    await db.commit()


async def fusionar_skills(db: AsyncSession, actor: Actor, id_origen: int, id_destino: int) -> None:
    """Mueve las personas de `origen` a `destino` (conservando el nivel más alto) y elimina `origen`."""
    exigir(actor.gestiona_equipo, MSG_CATALOGO)
    if id_origen == id_destino:
        raise ConflictError("Elige un skill distinto para fusionar")
    origen, destino = await _skill(db, id_origen), await _skill(db, id_destino)

    orden = {"Básico": 1, "Intermedio": 2, "Experto": 3}
    en_destino = {us.id_usuario: us for us in await db.scalars(select(UsuarioSkill).where(UsuarioSkill.id_skill == id_destino))}
    for us in list(await db.scalars(select(UsuarioSkill).where(UsuarioSkill.id_skill == id_origen))):
        previo = en_destino.get(us.id_usuario)
        if previo is not None:
            if orden[us.nivel] > orden[previo.nivel]:
                previo.nivel = us.nivel
            await db.delete(us)
    await db.flush()
    await db.execute(update(UsuarioSkill).where(UsuarioSkill.id_skill == id_origen).values(id_skill=id_destino))
    auditoria_service.registrar(
        db, actor, entidad="skill", id_entidad=id_destino, accion="fusion",
        resumen=f"Skill «{origen.nombre}» fusionado en «{destino.nombre}»",
    )
    await db.delete(origen)
    await db.commit()


async def eliminar_skill(db: AsyncSession, actor: Actor, id_skill: int) -> None:
    exigir(actor.gestiona_equipo, MSG_CATALOGO)
    skill = await _skill(db, id_skill)
    auditoria_service.registrar(
        db, actor, entidad="skill", id_entidad=id_skill, accion="baja", resumen=f"Skill «{skill.nombre}» eliminado"
    )
    await db.delete(skill)
    await db.commit()


# ---------- Ausencias ----------
async def _exigir_gestion_ausencias(actor: Actor, usuario: Usuario) -> None:
    exigir(
        actor.id_usuario == usuario.id_usuario or actor.gestiona_departamento(usuario.departamento),
        "Solo la propia persona o su gerente pueden gestionar sus ausencias",
    )


async def listar_ausencias(db: AsyncSession, id_usuario: int) -> list[Ausencia]:
    await obtener_usuario(db, id_usuario)
    return list(
        await db.scalars(select(Ausencia).where(Ausencia.id_usuario == id_usuario).order_by(Ausencia.fecha_inicio.desc()))
    )


async def crear_ausencia(db: AsyncSession, actor: Actor, id_usuario: int, data: AusenciaCreate) -> Ausencia:
    usuario = await obtener_usuario(db, id_usuario)
    await _exigir_gestion_ausencias(actor, usuario)
    traslape = await db.scalar(
        select(Ausencia.id_ausencia).where(
            Ausencia.id_usuario == id_usuario,
            Ausencia.fecha_inicio <= data.fecha_fin,
            Ausencia.fecha_fin >= data.fecha_inicio,
        )
    )
    if traslape is not None:
        raise ConflictError("Ya hay una ausencia registrada que se traslapa con esas fechas")
    ausencia = Ausencia(id_usuario=id_usuario, **data.model_dump())
    db.add(ausencia)
    await db.flush()
    auditoria_service.registrar(
        db, actor, entidad="ausencia", id_entidad=ausencia.id_ausencia, id_usuario_afectado=id_usuario,
        accion="alta", resumen=f"{data.tipo.value}: {data.fecha_inicio:%d/%m/%Y} – {data.fecha_fin:%d/%m/%Y}",
    )
    await db.commit()
    await db.refresh(ausencia)
    return ausencia


async def eliminar_ausencia(db: AsyncSession, actor: Actor, id_ausencia: int) -> None:
    ausencia = await db.get(Ausencia, id_ausencia)
    if ausencia is None:
        raise NotFoundError(f"Ausencia con id {id_ausencia} no existe")
    await _exigir_gestion_ausencias(actor, await obtener_usuario(db, ausencia.id_usuario))
    auditoria_service.registrar(
        db, actor, entidad="ausencia", id_entidad=id_ausencia, id_usuario_afectado=ausencia.id_usuario, accion="baja",
        resumen=f"{ausencia.tipo} eliminada: {ausencia.fecha_inicio:%d/%m/%Y} – {ausencia.fecha_fin:%d/%m/%Y}",
    )
    await db.delete(ausencia)
    await db.commit()


# ---------- Asignaciones de una persona ----------
async def asignaciones_de_persona(db: AsyncSession, actor: Actor, id_usuario: int) -> list[AsignacionPersonaRead]:
    usuario = await obtener_usuario(db, id_usuario)
    filas = await db.execute(
        select(AsignacionRecurso, EtapaProyecto, Proyecto)
        .join(EtapaProyecto, EtapaProyecto.id_etapa == AsignacionRecurso.id_etapa)
        .join(Proyecto, Proyecto.id_proyecto == AsignacionRecurso.id_proyecto)
        .where(AsignacionRecurso.id_usuario == id_usuario, *(c for c in [visibilidad.condicion(actor)] if c is not None))
        .order_by(EtapaProyecto.fecha_inicio_est.desc().nulls_first(), AsignacionRecurso.id_asignacion.desc())
    )
    costo = usuario.costo_hora if actor.ve_costos else None
    horas = dict(
        (id_etapa, h) for id_etapa, h in await db.execute(
            select(Tarea.id_etapa, func.sum(Tarea.horas_asignadas)).where(Tarea.id_usuario == id_usuario).group_by(Tarea.id_etapa)
        )
    )
    return [
        AsignacionPersonaRead(
            id_asignacion=a.id_asignacion,
            id_proyecto=p.id_proyecto,
            nombre_proyecto=p.nombre_proyecto,
            estado_proyecto=p.estado_proyecto,
            id_etapa=e.id_etapa,
            nombre_etapa=e.nombre_etapa,
            estado_etapa=e.estado_etapa,
            fecha_inicio_est=e.fecha_inicio_est,
            fecha_fin_est=e.fecha_fin_est,
            perfil_requerido=a.perfil_requerido,
            horas_en_tareas=horas.get(e.id_etapa, Decimal(0)),
            vigente=e.estado_etapa not in ESTADOS_ETAPA_SIN_CARGA and p.estado_proyecto not in ESTADOS_PROYECTO_SIN_CARGA,
            costo_estimado=(horas.get(e.id_etapa, Decimal(0)) * costo).quantize(Decimal("0.01")) if costo is not None else None,
        )
        for a, e, p in filas
    ]
