"""Proyecto: + fecha de inicio y presupuesto de horas

Ambos opcionales. Delimitan las tareas: sus fechas deben caer entre `fecha_inicio` y la fecha
comprometida (o tentativa), y la suma de sus horas no puede exceder `horas_presupuestadas`.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columnas = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("proyecto")}
    if "fecha_inicio" not in columnas:
        op.add_column("proyecto", sa.Column("fecha_inicio", sa.Date(), nullable=True))
    if "horas_presupuestadas" not in columnas:
        op.add_column("proyecto", sa.Column("horas_presupuestadas", sa.Numeric(10, 2), nullable=True))
        op.create_check_constraint(
            "horas_presupuestadas_no_negativas", "proyecto", "horas_presupuestadas IS NULL OR horas_presupuestadas >= 0"
        )


def downgrade() -> None:
    op.drop_column("proyecto", "horas_presupuestadas")  # arrastra su CHECK
    op.drop_column("proyecto", "fecha_inicio")
