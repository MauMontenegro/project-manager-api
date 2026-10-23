"""Tareas recurrentes (operación)

- `tarea_recurrente` (+ `tarea_recurrente_etiqueta`): plantillas diarias, semanales o mensuales de una persona.
- `tarea`: `id_proyecto` e `id_etapa` admiten nulo; + `id_recurrente`, + `periodo`. Una tarea es de proyecto
  (proyecto + etapa) o de un periodo de una recurrente (recurrente + periodo), nunca ambas.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tarea_recurrente",
        sa.Column("id_recurrente", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text()),
        sa.Column(
            "id_usuario", sa.BigInteger(),
            sa.ForeignKey("usuario.id_usuario", name="fk_tarea_recurrente_id_usuario_usuario",
                          ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False,
        ),
        sa.Column("frecuencia", sa.String(20), nullable=False),
        sa.Column("horas_por_periodo", sa.Numeric(8, 2), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date()),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("generada_hasta", sa.Date()),
        sa.Column(
            "id_creador", sa.BigInteger(),
            sa.ForeignKey("usuario.id_usuario", name="fk_tarea_recurrente_id_creador_usuario",
                          ondelete="SET NULL", onupdate="CASCADE"),
        ),
        sa.Column("fecha_creacion", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("frecuencia IN ('Diaria', 'Semanal', 'Mensual')", name="frecuencia"),
        sa.CheckConstraint("horas_por_periodo >= 0", name="horas_no_negativas"),
        sa.CheckConstraint("fecha_fin IS NULL OR fecha_fin >= fecha_inicio", name="fechas_validas"),
    )
    op.create_index("ix_tarea_recurrente_id_usuario", "tarea_recurrente", ["id_usuario"])
    op.create_table(
        "tarea_recurrente_etiqueta",
        sa.Column(
            "id_recurrente", sa.BigInteger(),
            sa.ForeignKey("tarea_recurrente.id_recurrente", name="fk_tarea_recurrente_etiqueta_id_recurrente_tarea_recurrente",
                          ondelete="CASCADE", onupdate="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "id_etiqueta", sa.BigInteger(),
            sa.ForeignKey("etiqueta.id_etiqueta", name="fk_tarea_recurrente_etiqueta_id_etiqueta_etiqueta",
                          ondelete="CASCADE", onupdate="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("ix_tarea_recurrente_etiqueta_id_etiqueta", "tarea_recurrente_etiqueta", ["id_etiqueta"])

    op.alter_column("tarea", "id_proyecto", nullable=True)
    op.alter_column("tarea", "id_etapa", nullable=True)
    op.add_column(
        "tarea",
        sa.Column(
            "id_recurrente", sa.BigInteger(),
            sa.ForeignKey("tarea_recurrente.id_recurrente", name="fk_tarea_id_recurrente_tarea_recurrente",
                          ondelete="CASCADE", onupdate="CASCADE"),
        ),
    )
    op.add_column("tarea", sa.Column("periodo", sa.Date()))
    op.create_index("ix_tarea_id_recurrente", "tarea", ["id_recurrente"])
    op.create_unique_constraint("uq_tarea_recurrente_periodo", "tarea", ["id_recurrente", "periodo"])
    op.create_check_constraint(
        "origen_valido", "tarea",
        "(id_recurrente IS NULL AND id_proyecto IS NOT NULL AND id_etapa IS NOT NULL AND periodo IS NULL)"
        " OR (id_recurrente IS NOT NULL AND id_proyecto IS NULL AND id_etapa IS NULL AND periodo IS NOT NULL)",
    )


def downgrade() -> None:
    op.execute("DELETE FROM tarea WHERE id_recurrente IS NOT NULL")
    op.drop_constraint("origen_valido", "tarea", type_="check")
    op.drop_constraint("uq_tarea_recurrente_periodo", "tarea", type_="unique")
    op.drop_index("ix_tarea_id_recurrente", "tarea")
    op.drop_column("tarea", "periodo")
    op.drop_column("tarea", "id_recurrente")
    op.alter_column("tarea", "id_etapa", nullable=False)
    op.alter_column("tarea", "id_proyecto", nullable=False)
    op.drop_table("tarea_recurrente_etiqueta")
    op.drop_table("tarea_recurrente")
