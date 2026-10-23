from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import CurrentActor, exigir
from app.models.enums import Departamento, NivelSkill, TipoRecurso
from app.schemas.equipo import (
    BitacoraRead,
    CapacidadPersona,
    SesionRead,
    SkillCatalogoRead,
    SkillFusionar,
    SkillRenombrar,
)
from app.schemas.usuario import PerfilUpdate, PuestoCreate, PuestoRead, UsuarioRead
from app.services import auditoria_service, capacidad_service, equipo_service, usuario_service

router = APIRouter(tags=["Equipo"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/sesion", response_model=SesionRead)
async def sesion(actor: CurrentActor):
    """Usuario autenticado y su rol, para adaptar la interfaz."""
    return SesionRead(
        id_usuario=actor.id_usuario,
        nombre=actor.nombre,
        correo=actor.correo,
        rol=actor.rol,
        departamento=actor.departamento,
        auth_habilitada=settings.AUTH_ENABLED,
        password_temporal=actor.password_temporal,
        asistente_disponible=bool(settings.ASISTENTE_URL) and actor.id_usuario is not None,
    )


@router.get("/perfil", response_model=UsuarioRead)
async def obtener_perfil(db: DbSession, actor: CurrentActor):
    """Ficha de quien inició sesión. `404` si la sesión no está ligada a una persona del Equipo."""
    return usuario_service.a_lectura(await usuario_service.obtener_perfil(db, actor), actor)


@router.patch("/perfil", response_model=UsuarioRead)
async def actualizar_perfil(data: PerfilUpdate, db: DbSession, actor: CurrentActor):
    """Cada persona edita su nombre y sus skills. Lo demás lo cambia su gerente."""
    return usuario_service.a_lectura(await usuario_service.actualizar_perfil(db, actor, data), actor)


# ---------- Puestos ----------
@router.get("/puestos", response_model=list[PuestoRead])
async def listar_puestos(db: DbSession):
    return await equipo_service.listar_puestos(db)


@router.post("/puestos", response_model=PuestoRead, status_code=status.HTTP_201_CREATED)
async def crear_puesto(data: PuestoCreate, db: DbSession, actor: CurrentActor):
    return await equipo_service.crear_puesto(db, actor, data)


@router.delete("/puestos/{id_puesto}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_puesto(id_puesto: int, db: DbSession, actor: CurrentActor):
    """Solo se elimina si ninguna persona tiene el puesto (409 en caso contrario)."""
    await equipo_service.eliminar_puesto(db, actor, id_puesto)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- Catálogo de skills ----------
@router.get("/skills", response_model=list[SkillCatalogoRead])
async def listar_skills(db: DbSession):
    """Catálogo con el número de personas que tiene cada skill."""
    return await equipo_service.listar_skills(db)


@router.patch("/skills/{id_skill}", status_code=status.HTTP_204_NO_CONTENT)
async def renombrar_skill(id_skill: int, data: SkillRenombrar, db: DbSession, actor: CurrentActor):
    await equipo_service.renombrar_skill(db, actor, id_skill, data.nombre)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/skills/{id_skill}/fusionar", status_code=status.HTTP_204_NO_CONTENT)
async def fusionar_skill(id_skill: int, data: SkillFusionar, db: DbSession, actor: CurrentActor):
    """Unifica variantes (p. ej. «ReactJS» → «React») conservando el nivel más alto de cada persona."""
    await equipo_service.fusionar_skills(db, actor, id_skill, data.id_destino)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/skills/{id_skill}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_skill(id_skill: int, db: DbSession, actor: CurrentActor):
    """Elimina el skill del catálogo y de todas las personas que lo tenían."""
    await equipo_service.eliminar_skill(db, actor, id_skill)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- Ausencias ----------
@router.delete("/ausencias/{id_ausencia}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_ausencia(id_ausencia: int, db: DbSession, actor: CurrentActor):
    await equipo_service.eliminar_ausencia(db, actor, id_ausencia)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- Capacidad ----------
@router.get("/capacidad", response_model=list[CapacidadPersona])
async def capacidad(
    db: DbSession,
    desde: Annotated[date | None, Query(description="Se ajusta al lunes de esa semana; por defecto, hoy")] = None,
    semanas: Annotated[int, Query(ge=1, le=26)] = 12,
    id_usuario: int | None = None,
    departamento: Departamento | None = None,
    id_puesto: int | None = None,
    tipo_recurso: TipoRecurso | None = None,
    skill: str | None = None,
    nivel_min: NivelSkill | None = None,
):
    """Horas disponibles, asignadas y % de utilización por persona activa y semana."""
    if id_usuario is not None:
        usuarios = [await usuario_service.obtener_usuario(db, id_usuario)]
    else:
        usuarios = await usuario_service.listar_usuarios(
            db, departamento=departamento, id_puesto=id_puesto, tipo_recurso=tipo_recurso, skill=skill,
            nivel_min=nivel_min, activo=True, limit=200,
        )
    return await capacidad_service.calcular(db, usuarios, desde or date.today(), semanas)


# ---------- Bitácora ----------
@router.get("/bitacora", response_model=list[BitacoraRead])
async def bitacora(
    db: DbSession,
    actor: CurrentActor,
    entidad: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Últimos cambios registrados. Solo Administrador y Gerentes."""
    exigir(actor.gestiona_equipo)
    return await auditoria_service.listar(db, entidad=entidad, limit=limit)
