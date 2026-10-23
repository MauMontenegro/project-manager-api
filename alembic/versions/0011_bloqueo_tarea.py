"""Bloqueo: + actividad (tarea) relacionada, opcional

`bloqueo_interrupcion.id_tarea` → `tarea` (SET NULL al borrar la tarea: el bloqueo queda en la etapa).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

T = "bloqueo_interrupcion"


def upgrade() -> None:
    if "id_tarea" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(T)}:
        return
    op.add_column(T, sa.Column("id_tarea", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        f"fk_{T}_id_tarea_tarea", T, "tarea", ["id_tarea"], ["id_tarea"], ondelete="SET NULL", onupdate="CASCADE"
    )
    op.create_index(f"ix_{T}_id_tarea", T, ["id_tarea"])


def downgrade() -> None:
    op.drop_column(T, "id_tarea")  # arrastra su FK e índice
