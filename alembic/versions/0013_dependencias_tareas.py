"""Dependencias entre tareas

- `tarea_dependencia` (id_tarea, id_dependencia): la tarea no sale de `Pendiente` hasta que sus
  dependencias estén `Finalizado`.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CASCADE = {"ondelete": "CASCADE", "onupdate": "CASCADE"}


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("tarea_dependencia"):
        return
    op.create_table(
        "tarea_dependencia",
        sa.Column("id_tarea", sa.BigInteger(), nullable=False),
        sa.Column("id_dependencia", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id_tarea", "id_dependencia", name="pk_tarea_dependencia"),
        sa.ForeignKeyConstraint(["id_tarea"], ["tarea.id_tarea"], name="fk_tarea_dependencia_id_tarea_tarea", **CASCADE),
        sa.ForeignKeyConstraint(
            ["id_dependencia"], ["tarea.id_tarea"], name="fk_tarea_dependencia_id_dependencia_tarea", **CASCADE
        ),
        sa.CheckConstraint("id_tarea <> id_dependencia", name="sin_autodependencia"),
    )
    op.create_index("ix_tarea_dependencia_id_dependencia", "tarea_dependencia", ["id_dependencia"])


def downgrade() -> None:
    op.drop_table("tarea_dependencia")
