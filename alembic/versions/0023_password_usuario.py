"""Inicio de sesión con correo y contraseña

- `usuario.password_hash` (scrypt; nulo = la persona aún no tiene contraseña).
- `usuario.password_temporal`: asignada por un administrador; se exige cambiarla al entrar.
- `usuario.password_actualizada`: invalida las sesiones emitidas antes del último cambio.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuario", sa.Column("password_hash", sa.String(255)))
    op.add_column("usuario", sa.Column("password_temporal", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("usuario", sa.Column("password_actualizada", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("usuario", "password_actualizada")
    op.drop_column("usuario", "password_temporal")
    op.drop_column("usuario", "password_hash")
