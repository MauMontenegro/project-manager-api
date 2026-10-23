"""Horas reales de las tareas

- `tarea.horas_reales`: horas que realmente tomó la tarea; se registran al finalizarla y permiten
  comparar lo estimado contra lo real.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "horas_reales" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tarea")}:
        return
    op.add_column("tarea", sa.Column("horas_reales", sa.Numeric(8, 2), nullable=True))
    op.create_check_constraint("horas_reales_no_negativas", "tarea", "horas_reales IS NULL OR horas_reales >= 0")


def downgrade() -> None:
    op.drop_column("tarea", "horas_reales")
