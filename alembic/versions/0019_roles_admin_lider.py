"""Roles de acceso: Administrador, Gerente, Líder y Usuario

`Director` pasa a `Administrador` (mismos permisos) y `Colaborador` a `Usuario`; se agrega `Líder`
(crea proyectos en su departamento y gestiona los que lidera).

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("rol", "usuario", type_="check")
    op.execute("UPDATE usuario SET rol = 'Administrador' WHERE rol = 'Director'")
    op.execute("UPDATE usuario SET rol = 'Usuario' WHERE rol = 'Colaborador'")
    op.alter_column("usuario", "rol", server_default="Usuario")
    op.create_check_constraint("rol", "usuario", "rol IN ('Administrador', 'Gerente', 'Líder', 'Usuario')")


def downgrade() -> None:
    op.drop_constraint("rol", "usuario", type_="check")
    op.execute("UPDATE usuario SET rol = 'Director' WHERE rol = 'Administrador'")
    op.execute("UPDATE usuario SET rol = 'Colaborador' WHERE rol IN ('Usuario', 'Líder')")
    op.alter_column("usuario", "rol", server_default="Colaborador")
    op.create_check_constraint("rol", "usuario", "rol IN ('Director', 'Gerente', 'Colaborador')")
