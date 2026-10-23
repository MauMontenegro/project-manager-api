"""Asigna una contraseña temporal desde la terminal (arranque inicial o si nadie más puede entrar).

    docker compose exec api python -m app.cli.password correo@empresa.com
    docker compose exec api python -m app.cli.password correo@empresa.com --crear "Nombre Apellido"

Con `--crear`, si no hay nadie con ese correo, da de alta a la persona como Administrador de Dirección (primer acceso
en una base vacía); su puesto y demás datos se completan después en la app.
Imprime la contraseña temporal; la persona debe cambiarla al entrar.
"""
import asyncio
import sys
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.core import passwords
import app.models  # noqa: F401  (registra todos los modelos)
from app.core.database import AsyncSessionLocal
from app.models.enums import Departamento, RolSistema
from app.models.equipo import Bitacora
from app.models.organizacion import Usuario


async def main(correo: str, nombre_nuevo: str | None = None) -> None:
    async with AsyncSessionLocal() as db:
        usuario = await db.scalar(select(Usuario).where(func.lower(Usuario.correo) == correo.lower()))
        if usuario is None and nombre_nuevo:
            usuario = Usuario(
                nombre=nombre_nuevo, correo=correo.lower(), rol=RolSistema.ADMINISTRADOR.value,
                departamento=Departamento.DIRECCION.value, capacidad_horas_semanales=Decimal(40),
            )
            db.add(usuario)
            await db.flush()
            print(f"Alta de {nombre_nuevo} ({correo}) como Administrador.")
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
    if len(sys.argv) == 2:
        asyncio.run(main(sys.argv[1]))
    elif len(sys.argv) == 4 and sys.argv[2] == "--crear":
        asyncio.run(main(sys.argv[1], sys.argv[3]))
    else:
        sys.exit(__doc__)
