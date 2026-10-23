"""Asigna una contraseña temporal desde la terminal (arranque inicial o si nadie más puede entrar).

    docker compose exec api python -m app.cli.password correo@empresa.com

Imprime la contraseña temporal; la persona debe cambiarla al entrar.
"""
import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core import passwords
import app.models  # noqa: F401  (registra todos los modelos)
from app.core.database import AsyncSessionLocal
from app.models.equipo import Bitacora
from app.models.organizacion import Usuario


async def main(correo: str) -> None:
    async with AsyncSessionLocal() as db:
        usuario = await db.scalar(select(Usuario).where(func.lower(Usuario.correo) == correo.lower()))
        if usuario is None or not usuario.activo:
            sys.exit(f"No hay una persona activa con el correo {correo}")
        temporal = passwords.generar_temporal()
        usuario.password_hash = passwords.hashear(temporal)
        usuario.password_temporal = True
        usuario.password_actualizada = datetime.now(UTC)
        db.add(Bitacora(
            id_actor=None, actor_nombre="Consola del servidor", entidad="usuario", id_entidad=usuario.id_usuario,
            id_usuario_afectado=usuario.id_usuario, accion="password",
            resumen=f"Asignó una contraseña temporal a {usuario.nombre}",
        ))
        await db.commit()
        print(f"Contraseña temporal de {usuario.nombre} ({usuario.correo}): {temporal}")
        print("Deberá cambiarla al iniciar sesión.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1]))
