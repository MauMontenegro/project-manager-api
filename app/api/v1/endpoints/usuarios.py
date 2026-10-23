from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActor
from app.models.enums import Departamento, NivelSkill, TipoRecurso
from app.schemas.equipo import AsignacionPersonaRead, AusenciaCreate, AusenciaRead, BitacoraRead
from app.schemas.auth import PasswordTemporal, RestablecerPasswordIn
from app.schemas.usuario import UsuarioCreate, UsuarioRead, UsuarioUpdate
from app.services import auditoria_service, auth_service, equipo_service, usuario_service

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
async def crear_usuario(data: UsuarioCreate, db: DbSession, actor: CurrentActor):
    """Administrador: cualquier departamento. Gerente: solo el suyo y sin otorgar roles."""
    return usuario_service.a_lectura(await usuario_service.crear_usuario(db, actor, data), actor)


@router.get("", response_model=list[UsuarioRead])
async def listar_usuarios(
    db: DbSession,
    actor: CurrentActor,
    id_puesto: int | None = None,
    departamento: Departamento | None = None,
    tipo_recurso: TipoRecurso | None = None,
    id_jefe: int | None = None,
    skill: Annotated[str | None, Query(description="Personas con este skill (sin distinguir mayúsculas)")] = None,
    nivel_min: Annotated[NivelSkill | None, Query(description="Nivel mínimo del skill indicado")] = None,
    activo: bool | None = None,
    q: Annotated[str | None, Query(description="Búsqueda por nombre o correo")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    usuarios = await usuario_service.listar_usuarios(
        db,
        id_puesto=id_puesto,
        departamento=departamento,
        tipo_recurso=tipo_recurso,
        id_jefe=id_jefe,
        skill=skill,
        nivel_min=nivel_min,
        activo=activo,
        busqueda=q,
        limit=limit,
        offset=offset,
    )
    return [usuario_service.a_lectura(u, actor) for u in usuarios]


@router.get("/{id_usuario}", response_model=UsuarioRead)
async def obtener_usuario(id_usuario: int, db: DbSession, actor: CurrentActor):
    return usuario_service.a_lectura(await usuario_service.obtener_usuario(db, id_usuario), actor)


@router.patch("/{id_usuario}", response_model=UsuarioRead)
async def actualizar_usuario(id_usuario: int, data: UsuarioUpdate, db: DbSession, actor: CurrentActor):
    return usuario_service.a_lectura(await usuario_service.actualizar_usuario(db, actor, id_usuario, data), actor)


@router.delete("/{id_usuario}", status_code=status.HTTP_204_NO_CONTENT)
async def desactivar_usuario(id_usuario: int, db: DbSession, actor: CurrentActor):
    """Baja lógica (`activo = false`); el registro se conserva por sus referencias históricas."""
    await usuario_service.desactivar_usuario(db, actor, id_usuario)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{id_usuario}/password", response_model=PasswordTemporal)
async def restablecer_password(id_usuario: int, data: RestablecerPasswordIn, db: DbSession, actor: CurrentActor):
    """Asigna una contraseña temporal (la indicada o una generada) que la persona debe cambiar al entrar.
    Administrador: a cualquiera. Gerente: a su departamento, salvo Administradores y Gerentes."""
    return PasswordTemporal(password_temporal=await auth_service.restablecer_password(db, actor, id_usuario, data.nueva))


@router.get("/{id_usuario}/asignaciones", response_model=list[AsignacionPersonaRead])
async def asignaciones_de_persona(id_usuario: int, db: DbSession, actor: CurrentActor):
    """Asignaciones vigentes e históricas, con proyecto y etapa resueltos."""
    return await equipo_service.asignaciones_de_persona(db, actor, id_usuario)


@router.get("/{id_usuario}/ausencias", response_model=list[AusenciaRead])
async def listar_ausencias(id_usuario: int, db: DbSession):
    return await equipo_service.listar_ausencias(db, id_usuario)


@router.post("/{id_usuario}/ausencias", response_model=AusenciaRead, status_code=status.HTTP_201_CREATED)
async def crear_ausencia(id_usuario: int, data: AusenciaCreate, db: DbSession, actor: CurrentActor):
    """La propia persona o quien gestiona su departamento. `409` si se traslapa con otra."""
    return await equipo_service.crear_ausencia(db, actor, id_usuario, data)


@router.get("/{id_usuario}/bitacora", response_model=list[BitacoraRead])
async def bitacora_de_persona(
    id_usuario: int, db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50
):
    return await auditoria_service.listar(db, id_usuario_afectado=id_usuario, limit=limit)


