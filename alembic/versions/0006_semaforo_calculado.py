"""Semáforo calculado: + motivo y fecha de cálculo

`proyecto.semaforo_motivo` explica el valor y `proyecto.semaforo_fecha` indica el día en que se
calculó. Quedan nulos: la API recalcula los proyectos abiertos al consultarlos.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columnas = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("proyecto")}
    if "semaforo_motivo" not in columnas:
        op.add_column("proyecto", sa.Column("semaforo_motivo", sa.String(200), nullable=True))
    if "semaforo_fecha" not in columnas:
        op.add_column("proyecto", sa.Column("semaforo_fecha", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("proyecto", "semaforo_fecha")
    op.drop_column("proyecto", "semaforo_motivo")
