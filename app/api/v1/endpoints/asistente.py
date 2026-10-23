import json
import logging
import time
from collections import defaultdict, deque
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import iam
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import ServiceUnavailableError, TooManyRequestsError
from app.core.security import CurrentActor, emitir_token_asistente, exigir
from app.schemas.asistente import ChatIn, SenalesAsistente, TokenAsistente
from app.services import asistente_service, usuario_service

router = APIRouter(prefix="/asistente", tags=["Asistente de IA"])
log = logging.getLogger(__name__)

DbSession = Annotated[AsyncSession, Depends(get_db)]
_preguntas: dict[int, deque[float]] = defaultdict(deque)
VENTANA_S = 10 * 60


def _exigir_persona(actor) -> None:
    exigir(actor.id_usuario is not None and not actor.asistente, "Solo una persona del Equipo con sesión puede usar el asistente")


@router.post("/token", response_model=TokenAsistente)
async def token_asistente(db: DbSession, actor: CurrentActor):
    """Token de solo lectura (15 min) para que el asistente consulte la API como esta persona: solo `GET` de proyectos,
    tareas, bloqueos, capacidad y señales, con la visibilidad de su rol. No se puede pedir con otro token del asistente."""
    _exigir_persona(actor)
    token, expira = emitir_token_asistente(await usuario_service.obtener_usuario(db, actor.id_usuario))
    return TokenAsistente(token=token, expira=expira)


@router.post("/chat")
async def chat(data: ChatIn, db: DbSession, actor: CurrentActor):
    """Pregunta al asistente. Responde en NDJSON mientras se genera (`sesion`, `estado`, `texto`, `final`, `fin` o
    `error`). Cada pregunta lleva un token nuevo de solo lectura de quien pregunta; el navegador nunca lo ve."""
    _exigir_persona(actor)
    if not settings.ASISTENTE_URL:
        raise ServiceUnavailableError("El asistente no está configurado")
    recientes = _preguntas[actor.id_usuario]
    limite = time.monotonic() - VENTANA_S
    while recientes and recientes[0] < limite:
        recientes.popleft()
    if len(recientes) >= settings.ASISTENTE_MAX_PREGUNTAS:
        raise TooManyRequestsError("Hiciste muchas preguntas seguidas. Espera unos minutos.")
    recientes.append(time.monotonic())

    token, _ = emitir_token_asistente(await usuario_service.obtener_usuario(db, actor.id_usuario))
    cuerpo = {
        "id_usuario": actor.id_usuario, "token": token, "mensaje": data.mensaje, "id_conversacion": data.id_conversacion,
        # Quién pregunta, de la sesión (no de lo que escriba la persona): así entiende "mi", "mis", "yo".
        "persona": {
            "id_usuario": actor.id_usuario, "nombre": actor.nombre, "rol": actor.rol.value,
            "departamento": actor.departamento.value if actor.departamento else None,
        },
    }
    error = (json.dumps({"tipo": "error", "mensaje": "El asistente no está disponible en este momento."}) + "\n").encode()

    base = settings.ASISTENTE_URL.rstrip("/")

    async def reenviar():
        try:
            headers = {"X-Agente-Clave": settings.ASISTENTE_CLAVE}
            if settings.ASISTENTE_IAM:
                headers |= await iam.encabezado(base)
            async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as cliente:
                async with cliente.stream("POST", f"{base}/chat", json=cuerpo, headers=headers) as r:
                    if r.status_code != 200:
                        log.warning("El agente respondió %s", r.status_code)
                        yield error
                        return
                    async for parte in r.aiter_bytes():
                        yield parte
        except Exception:  # noqa: BLE001  (red, identidad de Google o el propio agente)
            log.exception("No se pudo contactar al agente")
            yield error

    return StreamingResponse(reenviar(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})


@router.get("/senales", response_model=SenalesAsistente)
async def senales(db: DbSession, actor: CurrentActor):
    """Lo que pide atención en lo que la persona puede ver: proyectos en riesgo, tareas vencidas, bloqueos abiertos,
    esperas por dependencias, desfases grandes y sobrecarga. Calculado con reglas; el asistente lo explica y prioriza."""
    return await asistente_service.senales(db, actor)
