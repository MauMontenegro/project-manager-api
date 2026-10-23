"""Autenticación y política de permisos del Equipo.

Toda la API exige un `Actor`. Se acepta la sesión que emite esta API al entrar con correo y contraseña
(HS256, `SECRET_KEY`) o un ID token de Firebase (Google / Microsoft). Con `AUTH_ENABLED=false` el actor
es un Administrador local, de modo que el desarrollo no depende de ninguna de las dos.
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.models.enums import Departamento, RolSistema, TipoRecurso
from app.models.organizacion import Usuario

EMISOR_LOCAL = "petroil-pm"
FIREBASE_JWKS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
PROVEEDORES_OAUTH = {"google.com", "microsoft.com"}


@dataclass(frozen=True)
class Actor:
    """Quién hace la petición y con qué alcance."""

    id_usuario: int | None
    nombre: str
    correo: str | None
    rol: RolSistema
    departamento: Departamento | None
    # Entró con una contraseña temporal: solo puede consultar su sesión y cambiarla.
    password_temporal: bool = False
    # La petición la hace el asistente de IA en nombre de la persona (token de solo lectura).
    asistente: bool = False

    @property
    def es_admin(self) -> bool:
        return self.rol == RolSistema.ADMINISTRADOR

    @property
    def gestiona_equipo(self) -> bool:
        return self.rol in (RolSistema.ADMINISTRADOR, RolSistema.GERENTE)

    @property
    def ve_costos(self) -> bool:
        return self.gestiona_equipo

    def crea_proyectos_en(self, departamento: str | None) -> bool:
        """Administrador: en cualquiera. Gerente y Líder: en el suyo."""
        return self.es_admin or (
            self.rol in (RolSistema.GERENTE, RolSistema.LIDER) and departamento is not None and departamento == self.departamento
        )

    def gestiona_departamento(self, departamento: str | None) -> bool:
        """Administrador: cualquiera. Gerente: solo el suyo (y personas aún sin departamento)."""
        if self.es_admin:
            return True
        return self.rol == RolSistema.GERENTE and (departamento is None or departamento == self.departamento)

    def gestiona_proyecto(self, proyecto: Any) -> bool:
        """Administrador y líder del proyecto: siempre. Un conjunto, solo ellos; los demás proyectos, también el
        Gerente de su departamento (o cualquier Gerente si aún no tiene departamento)."""
        if self.es_admin or (self.id_usuario is not None and self.id_usuario == proyecto.lider_id):
            return True
        return not proyecto.es_conjunto and self.gestiona_departamento(proyecto.departamento)


ACTOR_LOCAL = Actor(id_usuario=None, nombre="Administrador local", correo=None, rol=RolSistema.ADMINISTRADOR, departamento=None)


def exigir(condicion: bool, mensaje: str = "No tienes permiso para realizar esta acción") -> None:
    if not condicion:
        raise ForbiddenError(mensaje)


@lru_cache
def _jwks() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(FIREBASE_JWKS_URL, cache_keys=True, lifespan=3600)


def _verificar_token(token: str) -> dict[str, Any]:
    """Valida firma, emisor, audiencia y vigencia del ID token de Firebase (llamada bloqueante)."""
    try:
        clave = _jwks().get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            clave,
            algorithms=["RS256"],
            audience=settings.FIREBASE_PROJECT_ID,
            issuer=f"https://securetoken.google.com/{settings.FIREBASE_PROJECT_ID}",
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Sesión inválida o expirada. Vuelve a iniciar sesión.") from exc


def _version_password(usuario: Usuario) -> int:
    return int(usuario.password_actualizada.timestamp() * 1000) if usuario.password_actualizada else 0


def emitir_sesion(usuario: Usuario) -> tuple[str, datetime]:
    """Token de sesión tras entrar con contraseña. Lleva la versión de la contraseña: al cambiarla o
    restablecerla, las sesiones anteriores dejan de valer."""
    ahora = datetime.now(UTC)
    expira = ahora + timedelta(hours=settings.SESION_HORAS)
    token = jwt.encode(
        {"iss": EMISOR_LOCAL, "sub": str(usuario.id_usuario), "iat": ahora, "exp": expira, "pwv": _version_password(usuario)},
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    return token, expira


# Token del asistente de IA: de una persona, de vida corta y solo para consultar (GET) estas rutas. Así el agente
# ve exactamente lo que ve la persona y no puede modificar nada aunque se le "convenza" de hacerlo.
ALCANCE_ASISTENTE = "asistente:lectura"
_RUTAS_ASISTENTE = tuple(
    f"{settings.API_V1_PREFIX}{r}"
    for r in (
        "/sesion", "/perfil", "/usuarios", "/proyectos", "/tareas", "/bloqueos", "/capacidad", "/equipos-trabajo",
        "/asistente/senales",
    )
)


def emitir_token_asistente(usuario: Usuario) -> tuple[str, datetime]:
    ahora = datetime.now(UTC)
    expira = ahora + timedelta(minutes=settings.ASISTENTE_TOKEN_MINUTOS)
    token = jwt.encode(
        {
            "iss": EMISOR_LOCAL, "sub": str(usuario.id_usuario), "iat": ahora, "exp": expira,
            "pwv": _version_password(usuario), "scope": ALCANCE_ASISTENTE,
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    return token, expira


def _es_sesion_local(token: str) -> bool:
    try:
        return jwt.get_unverified_header(token).get("alg") == "HS256"
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Sesión inválida o expirada. Vuelve a iniciar sesión.") from exc


# Lo único permitido con una contraseña temporal (además de entrar).
_RUTAS_CON_TEMPORAL = {f"{settings.API_V1_PREFIX}/sesion", f"{settings.API_V1_PREFIX}/auth/password"}


async def _actor_sesion_local(db: AsyncSession, token: str, ruta: str, metodo: str) -> Actor:
    try:
        claims = jwt.decode(
            token, settings.SECRET_KEY, algorithms=["HS256"], issuer=EMISOR_LOCAL,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
        id_usuario = int(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise UnauthorizedError("Sesión inválida o expirada. Vuelve a iniciar sesión.") from exc

    asistente = claims.get("scope") == ALCANCE_ASISTENTE
    usuario = await db.get(Usuario, id_usuario)
    if (
        usuario is None or not usuario.activo or usuario.tipo_recurso == TipoRecurso.ACTIVO.value
        # Quien entra con Google/Microsoft no tiene contraseña, pero sí puede usar el asistente.
        or (usuario.password_hash is None and not asistente) or claims.get("pwv") != _version_password(usuario)
    ):
        raise UnauthorizedError("Tu sesión ya no es válida. Vuelve a iniciar sesión.")
    if asistente and (metodo != "GET" or not ruta.startswith(_RUTAS_ASISTENTE) or usuario.password_temporal):
        raise ForbiddenError("El asistente solo puede consultar información")
    if usuario.password_temporal and ruta not in _RUTAS_CON_TEMPORAL:
        raise ForbiddenError("Cambia tu contraseña temporal para continuar")
    return Actor(
        id_usuario=usuario.id_usuario, nombre=usuario.nombre, correo=usuario.correo, rol=RolSistema(usuario.rol),
        departamento=Departamento(usuario.departamento) if usuario.departamento else None,
        password_temporal=usuario.password_temporal, asistente=asistente,
    )


async def get_actor(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> Actor:
    if not settings.AUTH_ENABLED:
        persona = await db.get(Usuario, settings.LOCAL_ID_USUARIO) if settings.LOCAL_ID_USUARIO else None
        if persona is None or not persona.activo:
            return ACTOR_LOCAL
        return Actor(
            id_usuario=persona.id_usuario, nombre=persona.nombre, correo=persona.correo, rol=RolSistema(persona.rol),
            departamento=Departamento(persona.departamento) if persona.departamento else None,
        )

    esquema, _, token = (authorization or "").partition(" ")
    if esquema.lower() != "bearer" or not token:
        raise UnauthorizedError("Falta el token de autenticación")
    if _es_sesion_local(token):
        return await _actor_sesion_local(db, token, request.url.path, request.method)
    claims = await run_in_threadpool(_verificar_token, token)

    correo = (claims.get("email") or "").lower()
    proveedor = claims.get("firebase", {}).get("sign_in_provider")
    if not correo or not (claims.get("email_verified") or proveedor in PROVEEDORES_OAUTH):
        raise UnauthorizedError("La cuenta no tiene un correo verificado")

    usuario = await db.scalar(
        select(Usuario).where(
            func.lower(Usuario.correo) == correo,
            Usuario.activo.is_(True),
            Usuario.tipo_recurso != TipoRecurso.ACTIVO.value,
        )
    )
    es_bootstrap = correo in {c.lower() for c in settings.BOOTSTRAP_ADMIN_EMAILS}
    if usuario is None and not es_bootstrap:
        raise ForbiddenError(f"La cuenta {correo} no está registrada en el Equipo. Pide acceso a tu gerente.")

    return Actor(
        id_usuario=usuario.id_usuario if usuario else None,
        nombre=usuario.nombre if usuario else claims.get("name", correo),
        correo=correo,
        rol=RolSistema.ADMINISTRADOR if es_bootstrap else RolSistema(usuario.rol),
        departamento=Departamento(usuario.departamento) if usuario and usuario.departamento else None,
    )


CurrentActor = Annotated[Actor, Depends(get_actor)]
