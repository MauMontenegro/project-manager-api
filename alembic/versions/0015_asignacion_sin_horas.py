"""Asignaciones sin dedicación ni horas

La asignación solo dice quién participa en qué etapa y con qué rol; la carga de cada persona sale
de sus tareas. Se eliminan `asignacion_recurso.horas_asignadas` y `porcentaje_utilizacion`
(con sus restricciones).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columnas = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("asignacion_recurso")}
    for columna in ("horas_asignadas", "porcentaje_utilizacion"):
        if columna in columnas:
            op.drop_column("asignacion_recurso", columna)


def downgrade() -> None:
    # Los valores eliminados no se recuperan: vuelven como columnas opcionales.
    op.add_column("asignacion_recurso", sa.Column("horas_asignadas", sa.Numeric(8, 2), nullable=True))
    op.add_column("asignacion_recurso", sa.Column("porcentaje_utilizacion", sa.Numeric(5, 2), nullable=True))
