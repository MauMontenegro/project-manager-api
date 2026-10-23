"""Equipos de trabajo (workspaces)

- `equipo_trabajo` (nombre único sin distinguir mayúsculas, descripción, color).
- `equipo_trabajo_miembro`: personas del equipo (una persona puede estar en varios).
- `proyecto.id_equipo_trabajo` (opcional; SET NULL al borrar el equipo).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CASCADE = {"ondelete": "CASCADE", "onupdate": "CASCADE"}


def upgrade() -> None:
    op.create_table(
        "equipo_trabajo",
        sa.Column("id_equipo_trabajo", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("fecha_creacion", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id_equipo_trabajo", name="pk_equipo_trabajo"),
        sa.CheckConstraint("color ~ '^#[0-9a-fA-F]{6}$'", name="color_hex"),
    )
    op.create_index("uq_equipo_trabajo_nombre", "equipo_trabajo", [sa.text("lower(nombre)")], unique=True)
    op.create_table(
        "equipo_trabajo_miembro",
        sa.Column("id_equipo_trabajo", sa.BigInteger(), nullable=False),
        sa.Column("id_usuario", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id_equipo_trabajo", "id_usuario", name="pk_equipo_trabajo_miembro"),
        sa.ForeignKeyConstraint(["id_equipo_trabajo"], ["equipo_trabajo.id_equipo_trabajo"],
                                name="fk_equipo_trabajo_miembro_id_equipo_trabajo_equipo_trabajo", **CASCADE),
        sa.ForeignKeyConstraint(["id_usuario"], ["usuario.id_usuario"], name="fk_equipo_trabajo_miembro_id_usuario_usuario", **CASCADE),
    )
    op.create_index("ix_equipo_trabajo_miembro_id_usuario", "equipo_trabajo_miembro", ["id_usuario"])
    op.add_column("proyecto", sa.Column("id_equipo_trabajo", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_proyecto_id_equipo_trabajo_equipo_trabajo", "proyecto", "equipo_trabajo", ["id_equipo_trabajo"], ["id_equipo_trabajo"],
        ondelete="SET NULL", onupdate="CASCADE",
    )
    op.create_index("ix_proyecto_id_equipo_trabajo", "proyecto", ["id_equipo_trabajo"])


def downgrade() -> None:
    op.drop_index("ix_proyecto_id_equipo_trabajo", "proyecto")
    op.drop_constraint("fk_proyecto_id_equipo_trabajo_equipo_trabajo", "proyecto", type_="foreignkey")
    op.drop_column("proyecto", "id_equipo_trabajo")
    op.drop_table("equipo_trabajo_miembro")
    op.drop_table("equipo_trabajo")
