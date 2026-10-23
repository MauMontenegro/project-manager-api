"""Identidad de Google entre servicios de Cloud Run privados (`--no-allow-unauthenticated`).

Cloud Run valida un ID token de la cuenta de servicio que llama. Va en `X-Serverless-Authorization` para dejar libre
`Authorization` para lo propio de cada servicio.
"""
import asyncio
import time

import google.auth.transport.requests
from google.oauth2 import id_token

_cache: dict[str, tuple[str, float]] = {}


async def encabezado(audiencia: str) -> dict[str, str]:
    """`{"X-Serverless-Authorization": "Bearer …"}` para llamar al servicio `audiencia` (su URL base)."""
    token, vence = _cache.get(audiencia, ("", 0.0))
    if time.monotonic() > vence:
        token = await asyncio.to_thread(id_token.fetch_id_token, google.auth.transport.requests.Request(), audiencia)
        _cache[audiencia] = (token, time.monotonic() + 50 * 60)  # duran 1 h
    return {"X-Serverless-Authorization": f"Bearer {token}"}
