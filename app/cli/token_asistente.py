"""Token de solo lectura del asistente para probar el agente en local (`adk web`), en nombre de una persona.

    docker compose exec api python -m app.cli.token_asistente correo@empresa.com

Dura ASISTENTE_TOKEN_MINUTOS (15 por defecto) y solo permite consultar lo que esa persona puede ver.
"""
import asyncio
import sys

from sqlalchemy import func, select

import app.models  # noqa: F401  (registra todos los modelos)
from app.core.database import AsyncSessionLocal
from app.core.security import emitir_token_asistente
from app.models.organizacion import Usuario


async def main(correo: str) -> None:
    async with AsyncSessionLocal() as db:
        usuario = await db.scalar(select(Usuario).where(func.lower(Usuario.correo) == correo.lower(), Usuario.activo.is_(True)))
        if usuario is None:
            sys.exit(f"No hay una persona activa con el correo {correo}")
        token, expira = emitir_token_asistente(usuario)
        print(token)
        print(f"# {usuario.nombre} · rol {usuario.rol} · vence {expira:%H:%M} UTC", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1]))
