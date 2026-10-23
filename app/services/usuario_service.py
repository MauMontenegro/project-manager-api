from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.security import Actor, exigir
from app.models.enums import Departamento, NivelSkill, RolSistema, TipoRecurso
from app.models.equipo import Skill, UsuarioSkill
from app.models.organizacion import Puesto, Usuario
from app.schemas.usuario import PerfilUpdate, SkillAsignada, UsuarioCreate, UsuarioRead, UsuarioUpdate
from app.services import auditoria_service

ORDEN_NIVEL = {NivelSkill.BASICO: 1, NivelSkill.INTERMEDIO: 2, NivelSkill.EXPERTO: 3}
CAMPOS_OBLIGATORIOS = {
    "tipo_recurso", "nombre", "departamento", "rol", "skills", "capacidad_horas_semanales", "porcentaje_proyectos",
    "activo",
}
CAMPOS_AUDITADOS = (
    "tipo_recurso", "nombre", "correo", "id_puesto", "departamento", "id_jefe", "rol", "capacidad_horas_semanales",
    "porcentaje_proyectos", "costo_hora", "proveedor", "fecha_fin_contrato", "activo",
)


def a_lectura(usuario: Usuario, actor: Actor) -> UsuarioRead:
    """Serializa ocultando el costo a quien no gestiona equipo."""
    leido = UsuarioRead.model_validate(usuario)
    return leido if actor.ve_costos else leido.model_copy(update={"costo_hora": None})


def _foto(usuario: Usuario) -> dict[str, Any]:
    return {
        **{campo: getattr(usuario, campo) for campo in CAMPOS_AUDITADOS},
        "skills": ", ".join(f"{s.nombre} ({s.nivel})" for s in usuario.skills),
    }


async def obtener_usuario(db: AsyncSession, id_usuario: int) -> Usuario:
    usuario = await db.scalar(
        select(Usuario).where(Usuario.id_usuario == id_usuario).execution_options(populate_existing=True)
    )
    if usuario is None:
        raise NotFoundError(f"Usuario con id {id_usuario} no existe")
    return usuario


async def listar_usuarios(
    db: AsyncSession,
    *,
    id_puesto: int | None = None,
    departamento: Departamento | None = None,
    tipo_recurso: TipoRecurso | None = None,
    id_jefe: int | None = None,
    skill: str | None = None,
    nivel_min: NivelSkill | None = None,
    activo: bool | None = None,
    busqueda: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Usuario]:
    stmt = select(Usuario)
    if id_puesto is not None:
        stmt = stmt.where(Usuario.id_puesto == id_puesto)
    if departamento is not None:
        stmt = stmt.where(Usuario.departamento == departamento.value)
    if tipo_recurso is not None:
        stmt = stmt.where(Usuario.tipo_recurso == tipo_recurso.value)
    if id_jefe is not None:
        stmt = stmt.where(Usuario.id_jefe == id_jefe)
    if skill:
        niveles = [n.value for n, orden in ORDEN_NIVEL.items() if orden >= ORDEN_NIVEL[nivel_min or NivelSkill.BASICO]]
        stmt = stmt.where(
            Usuario.skills.any(
                UsuarioSkill.skill.has(func.lower(Skill.nombre) == skill.lower()) & UsuarioSkill.nivel.in_(niveles)
            )
        )
    if activo is not None:
        stmt = stmt.where(Usuario.activo == activo)
    if busqueda:
        patron = f"%{busqueda}%"
        stmt = stmt.where(Usuario.nombre.ilike(patron) | Usuario.correo.ilike(patron))
    stmt = stmt.order_by(Usuario.nombre).limit(limit).offset(offset)
    return list(await db.scalars(stmt))


async def _validar(db: AsyncSession, usuario: Usuario) -> None:
    """Invariantes del recurso tras aplicar los cambios (alta o edición)."""
    tipo = TipoRecurso(usuario.tipo_recurso)
    if tipo != TipoRecurso.ACTIVO:
        if not usuario.correo:
            raise BusinessRuleError("El correo es obligatorio para personas")
        if usuario.id_puesto is None:
            raise BusinessRuleError("El puesto es obligatorio para personas")
    elif usuario.rol != RolSistema.USUARIO.value:
        raise BusinessRuleError("Un activo no puede tener rol de acceso distinto de Usuario")
    if tipo == TipoRecurso.EXTERNO and not usuario.proveedor:
        raise BusinessRuleError("Indica el proveedor del recurso externo")
    if tipo != TipoRecurso.EXTERNO:
        usuario.proveedor = None
        usuario.fecha_fin_contrato = None

    if usuario.id_puesto is not None and await db.get(Puesto, usuario.id_puesto) is None:
        raise NotFoundError(f"Puesto con id {usuario.id_puesto} no existe")

    if usuario.correo:
        stmt = select(Usuario.id_usuario).where(func.lower(Usuario.correo) == usuario.correo.lower())
        if usuario.id_usuario is not None:
            stmt = stmt.where(Usuario.id_usuario != usuario.id_usuario)
        if await db.scalar(stmt) is not None:
            raise ConflictError(f"El correo '{usuario.correo}' ya está registrado")

    if usuario.id_jefe is not None:
        await _validar_jefe(db, usuario)


async def _validar_jefe(db: AsyncSession, usuario: Usuario) -> None:
    jefe = await db.get(Usuario, usuario.id_jefe)
    if jefe is None:
        raise NotFoundError(f"Jefe con id {usuario.id_jefe} no existe")
    if jefe.tipo_recurso == TipoRecurso.ACTIVO.value:
        raise BusinessRuleError("Un activo no puede ser jefe de nadie")
    # Recorre la cadena hacia arriba: si se llega a la propia persona, habría un ciclo.
    visitados: set[int] = set()
    actual: Usuario | None = jefe
    while actual is not None and actual.id_usuario not in visitados:
        if usuario.id_usuario is not None and actual.id_usuario == usuario.id_usuario:
            raise BusinessRuleError(f"{jefe.nombre} reporta (directa o indirectamente) a {usuario.nombre}")
        visitados.add(actual.id_usuario)
        actual = await db.get(Usuario, actual.id_jefe) if actual.id_jefe else None


async def _sincronizar_skills(db: AsyncSession, usuario: Usuario, skills: list[SkillAsignada]) -> None:
    """Reemplaza los skills de la persona; los nombres nuevos se agregan al catálogo."""
    nombres = [s.nombre for s in skills]
    existentes = {
        s.nombre.lower(): s
        for s in await db.scalars(select(Skill).where(func.lower(Skill.nombre).in_([n.lower() for n in nombres])))
    }
    # Se reutilizan las filas que se conservan: borrar y reinsertar la misma PK en un
    # flush viola la unicidad (el unit of work inserta antes de borrar).
    actuales = {us.id_skill: us for us in usuario.skills}
    resultado = []
    for entrada in skills:
        skill = existentes.get(entrada.nombre.lower())
        if skill is None:
            skill = Skill(nombre=entrada.nombre)
            db.add(skill)
            existentes[entrada.nombre.lower()] = skill
        if skill.id_skill is not None and skill.id_skill in actuales:
            fila = actuales[skill.id_skill]
            fila.nivel = entrada.nivel.value
        else:
            fila = UsuarioSkill(skill=skill, nivel=entrada.nivel.value)
        resultado.append(fila)
    usuario.skills = resultado


ROLES_RESERVADOS = {RolSistema.ADMINISTRADOR.value, RolSistema.GERENTE.value}


def _exigir_alcance(actor: Actor, departamento: str | None, rol: str | None) -> None:
    exigir(actor.gestiona_departamento(departamento), "Solo puedes gestionar personas de tu departamento")
    if rol in ROLES_RESERVADOS:
        exigir(actor.es_admin, "Solo el Administrador puede otorgar roles de Gerente o Administrador")


async def crear_usuario(db: AsyncSession, actor: Actor, data: UsuarioCreate) -> Usuario:
    _exigir_alcance(actor, data.departamento.value, data.rol.value)
    usuario = Usuario(**data.model_dump(exclude={"skills"}))
    await _validar(db, usuario)
    await _sincronizar_skills(db, usuario, data.skills)
    db.add(usuario)
    await db.flush()
    auditoria_service.registrar(
        db, actor, entidad="usuario", id_entidad=usuario.id_usuario, id_usuario_afectado=usuario.id_usuario,
        accion="alta", resumen=f"Alta de {usuario.nombre}",
    )
    await db.commit()
    return await obtener_usuario(db, usuario.id_usuario)


async def actualizar_usuario(db: AsyncSession, actor: Actor, id_usuario: int, data: UsuarioUpdate) -> Usuario:
    usuario = await obtener_usuario(db, id_usuario)
    cambios = data.model_dump(exclude_unset=True)
    for campo in CAMPOS_OBLIGATORIOS & cambios.keys():
        if cambios[campo] is None:
            raise BusinessRuleError(f"{campo} no puede ser nulo")

    _exigir_alcance(actor, usuario.departamento, None)
    if "departamento" in cambios:
        _exigir_alcance(actor, cambios["departamento"], None)
    if "rol" in cambios and cambios["rol"] != usuario.rol:
        # Un Gerente puede alternar entre Usuario y Líder en su departamento; Gerente y Administrador, solo el Administrador.
        exigir(
            actor.es_admin or (cambios["rol"] not in ROLES_RESERVADOS and usuario.rol not in ROLES_RESERVADOS),
            "Solo el Administrador puede otorgar o quitar los roles de Gerente o Administrador",
        )

    antes = _foto(usuario)
    skills = data.skills if "skills" in cambios else None
    for campo, valor in cambios.items():
        if campo != "skills":
            setattr(usuario, campo, valor)
    await _validar(db, usuario)
    if skills is not None:
        await _sincronizar_skills(db, usuario, skills)
    await db.flush()

    diff = auditoria_service.diferencias(antes, _foto(usuario))
    if diff:
        accion = "reactivacion" if diff.get("activo") == [False, True] else "edicion"
        auditoria_service.registrar(
            db, actor, entidad="usuario", id_entidad=id_usuario, id_usuario_afectado=id_usuario,
            accion=accion, resumen=f"Cambios en {', '.join(diff)}", cambios=diff,
        )
    await db.commit()
    return await obtener_usuario(db, id_usuario)


async def obtener_perfil(db: AsyncSession, actor: Actor) -> Usuario:
    if actor.id_usuario is None:
        raise NotFoundError("Tu sesión no está ligada a una persona del Equipo")
    return await obtener_usuario(db, actor.id_usuario)


async def actualizar_perfil(db: AsyncSession, actor: Actor, data: PerfilUpdate) -> Usuario:
    """Cada persona edita su nombre y sus skills, sin depender de su gerente."""
    usuario = await obtener_perfil(db, actor)
    cambios = data.model_dump(exclude_unset=True)
    if "nombre" in cambios and cambios["nombre"] is None:
        raise BusinessRuleError("nombre no puede ser nulo")
    antes = _foto(usuario)
    if cambios.get("nombre"):
        usuario.nombre = cambios["nombre"].strip()
    if data.skills is not None and "skills" in cambios:
        await _sincronizar_skills(db, usuario, data.skills)
    await db.flush()
    diff = auditoria_service.diferencias(antes, _foto(usuario))
    if diff:
        auditoria_service.registrar(
            db, actor, entidad="usuario", id_entidad=usuario.id_usuario, id_usuario_afectado=usuario.id_usuario,
            accion="edicion", resumen=f"Actualizó su perfil: {', '.join(diff)}", cambios=diff,
        )
    await db.commit()
    return await obtener_usuario(db, usuario.id_usuario)


async def desactivar_usuario(db: AsyncSession, actor: Actor, id_usuario: int) -> None:
    """Baja lógica: el usuario puede estar referenciado por proyectos, solicitudes y avances (FK RESTRICT)."""
    usuario = await obtener_usuario(db, id_usuario)
    _exigir_alcance(actor, usuario.departamento, None)
    exigir(usuario.id_usuario != actor.id_usuario, "No puedes darte de baja a ti mismo")
    if usuario.activo:
        usuario.activo = False
        auditoria_service.registrar(
            db, actor, entidad="usuario", id_entidad=id_usuario, id_usuario_afectado=id_usuario,
            accion="baja", resumen=f"Baja de {usuario.nombre}",
        )
    await db.commit()
