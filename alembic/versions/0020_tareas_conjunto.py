"""Tareas propias del proyecto conjunto

Un conjunto no tiene etapas: sus tareas propias (las que no son de ningún subproyecto) van sin etapa.
La regla "etapa obligatoria salvo en un conjunto" la valida tarea_service.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RECURRENTE = "(id_recurrente IS NOT NULL AND id_proyecto IS NULL AND id_etapa IS NULL AND periodo IS NOT NULL)"


def upgrade() -> None:
    op.drop_constraint("origen_valido", "tarea", type_="check")
    op.create_check_constraint(
        "origen_valido", "tarea", f"(id_recurrente IS NULL AND id_proyecto IS NOT NULL AND periodo IS NULL) OR {RECURRENTE}"
    )


def downgrade() -> None:
    op.execute("DELETE FROM tarea WHERE id_recurrente IS NULL AND id_etapa IS NULL")
    op.drop_constraint("origen_valido", "tarea", type_="check")
    op.create_check_constraint(
        "origen_valido", "tarea",
        f"(id_recurrente IS NULL AND id_proyecto IS NOT NULL AND id_etapa IS NOT NULL AND periodo IS NULL) OR {RECURRENTE}",
    )
