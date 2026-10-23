"""Fechas de tarea obligatorias

La carga semanal de cada persona sale de sus tareas, repartidas entre sus fechas: una tarea sin
fechas no contaría. `tarea.fecha_inicio` y `fecha_fin` pasan a NOT NULL; las que falten se llenan
con la otra fecha o, si no hay ninguna, con el día de creación.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE tarea SET fecha_inicio = COALESCE(fecha_inicio, fecha_fin, fecha_creacion::date), "
        "fecha_fin = COALESCE(fecha_fin, fecha_inicio, fecha_creacion::date) "
        "WHERE fecha_inicio IS NULL OR fecha_fin IS NULL"
    )
    op.alter_column("tarea", "fecha_inicio", nullable=False)
    op.alter_column("tarea", "fecha_fin", nullable=False)


def downgrade() -> None:
    op.alter_column("tarea", "fecha_inicio", nullable=True)
    op.alter_column("tarea", "fecha_fin", nullable=True)
