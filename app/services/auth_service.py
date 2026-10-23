"""Inicio de sesión con correo y contraseña, cambio y restablecimiento de contraseña."""
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core import passwords
from app.core.exceptions import BusinessRuleError, TooManyRequestsError, UnauthorizedError
from app.core.security import Actor, emitir_sesion, exigir
from app.models.enums import RolSistema, TipoRecurso
from app.models.organizacion import Usuario
from app.schemas.auth import SesionToken
from app.services import auditoria_service, usuario_service

# Freno ante adivinanzas: tras 5 intentos fallidos en 15 minutos, la cuenta espera. En memoria del proceso.
MAX_INTENTOS = 5
VENTANA_S = 15 * 60
_fallidos: dict[str, deque[float]] = defaultdict(deque)

CREDENCIALES_INVALIDAS = "Correo o contraseña incorrectos"


def _recientes(correo: str) -> deque[float]:
    intentos = _fallidos[correo]
    limite = time.monotonic() - VENTANA_S
    while intentos and intentos[0] < limite:
        intentos.popleft()
    return intentos


def _token(usuario: Usuario) -> SesionToken:
    token, expira = emitir_sesion(usuario)
    return SesionToken(access_token=token, expira=expira, password_temporal=usuario.password_temporal)


async def _asignar(usuario: Usuario, password: str, *, temporal: bool) -> None:
    usuario.password_hash = await run_in_threadpool(passwords.hashear, password)
    usuario.password_temporal = temporal
    usuario.password_actualizada = datetime.now(UTC)


async def login(db: AsyncSession, correo: str, password: str) -> SesionToken:
    intentos = _recientes(correo)
    if len(intentos) >= MAX_INTENTOS:
        minutos = max(1, round((intentos[0] + VENTANA_S - time.monotonic()) / 60))
        raise TooManyRequestsError(f"Demasiados intentos fallidos. Espera {minutos} min y vuelve a intentarlo.")

    usuario = await db.scalar(
        select(Usuario).where(
            func.lower(Usuario.correo) == correo,
            Usuario.activo.is_(True),
            Usuario.tipo_recurso != TipoRecurso.ACTIVO.value,
        )
    )
    # Siempre se verifica (aun sin cuenta) para no revelar qué correos existen por el tiempo de respuesta.
    valida = await run_in_threadpool(passwords.verificar, password, usuario.password_hash if usuario else None)
    if usuario is None or not valida:
        intentos.append(time.monotonic())
        raise UnauthorizedError(CREDENCIALES_INVALIDAS)
    _fallidos.pop(correo, None)
    return _token(usuario)


async def cambiar_password(db: AsyncSession, actor: Actor, actual: str, nueva: str) -> SesionToken:
    """La propia persona. Devuelve una sesión nueva: las anteriores (en otros equipos) se cierran."""
    exigir(actor.id_usuario is not None, "Tu sesión no está ligada a una persona del Equipo")
    usuario = await usuario_service.obtener_usuario(db, actor.id_usuario)
    if not await run_in_threadpool(passwords.verificar, actual, usuario.password_hash):
        raise BusinessRuleError("La contraseña actual no es correcta")
    if actual == nueva:
        raise BusinessRuleError("La nueva contraseña debe ser distinta de la actual")
    passwords.validar_politica(nueva, correo=usuario.correo, nombre=usuario.nombre)
    await _asignar(usuario, nueva, temporal=False)
    auditoria_service.registrar(
        db, actor, entidad="usuario", id_entidad=usuario.id_usuario, id_usuario_afectado=usuario.id_usuario,
        accion="password", resumen="Cambió su contraseña",
    )
    await db.commit()
    return _token(usuario)


async def restablecer_password(db: AsyncSession, actor: Actor, id_usuario: int, nueva: str | None) -> str:
    """Administrador: a cualquiera. Gerente: a las personas de su departamento que no sean Administrador ni
    Gerente. Queda como temporal (se exige cambiarla al entrar) y cierra las sesiones abiertas de la persona."""
    usuario = await usuario_service.obtener_usuario(db, id_usuario)
    exigir(actor.id_usuario != id_usuario, "Para tu propia contraseña usa «Cambiar contraseña» en Mi perfil")
    exigir(
        actor.es_admin or (
            actor.gestiona_departamento(usuario.departamento)
            and usuario.rol not in (RolSistema.ADMINISTRADOR.value, RolSistema.GERENTE.value)
        ),
        "No puedes restablecer la contraseña de esta persona",
    )
    if not usuario.activo or usuario.tipo_recurso == TipoRecurso.ACTIVO.value or not usuario.correo:
        raise BusinessRuleError("Solo las personas activas con correo pueden iniciar sesión")
    temporal = nueva or passwords.generar_temporal()
    passwords.validar_politica(temporal, correo=usuario.correo, nombre=usuario.nombre)
    primera = usuario.password_hash is None
    await _asignar(usuario, temporal, temporal=True)
    auditoria_service.registrar(
        db, actor, entidad="usuario", id_entidad=usuario.id_usuario, id_usuario_afectado=usuario.id_usuario,
        accion="password",
        resumen=f"{'Asignó' if primera else 'Restableció'} una contraseña temporal a {usuario.nombre}",
    )
    await db.commit()
    _fallidos.pop(usuario.correo.lower(), None)
    return temporal
