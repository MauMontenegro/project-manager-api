"""Empresa impactada: + área de la empresa

`proyecto_empresa_impactada.id_area` (FK a `area`). Queda nulo en los registros existentes;
la API lo exige al crear proyectos nuevos.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columnas = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("proyecto_empresa_impactada")}
    if "id_area" in columnas:  # base nueva: 0001 ya la creó desde los modelos
        return
    op.add_column("proyecto_empresa_impactada", sa.Column("id_area", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_proyecto_empresa_impactada_id_area_area", "proyecto_empresa_impactada", "area", ["id_area"], ["id_area"],
        ondelete="RESTRICT", onupdate="CASCADE",
    )
    op.create_index("ix_proyecto_empresa_impactada_id_area", "proyecto_empresa_impactada", ["id_area"])


def downgrade() -> None:
    op.drop_column("proyecto_empresa_impactada", "id_area")  # arrastra su FK e índice
