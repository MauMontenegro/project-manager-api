"""Bloqueos de tareas, línea base y reprogramaciones (desfases)

- `tarea`: + `fecha_inicio_base`, `fecha_fin_base` (plan original; se fijan al crearla).
- `reprogramacion_tarea`: cada cambio de fechas de una tarea de proyecto (o nueva línea base), con su
  desfase en días hábiles, el motivo y, opcionalmente, el bloqueo que lo causó.
- `bloqueo_interrupcion`: + descripción, quién debe destrabarlo, fecha compromiso, nota de resolución,
  quién lo reportó, si es automático (espera de dependencia) y `horas_impacto`; `id_etapa` admite nulo
  (tareas generales de un conjunto); nueva causa `Dependencia Interna`. `dias_impacto` pasa a días hábiles.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

B = "bloqueo_interrupcion"
CAUSAS = [
    "Cambio de Prioridad", "Dependencia Externa", "Falta de Información", "Recurso Reasignado", "Incidente Operativo",
    "Cambio de Alcance", "Retrabajo", "Espera del Cliente", "Decisión Pendiente",
]


def _check_causas(causas: list[str]) -> str:
    return "causa_raiz IN (" + ", ".join(f"'{c}'" for c in causas) + ")"


def upgrade() -> None:
    op.add_column("tarea", sa.Column("fecha_inicio_base", sa.Date(), nullable=True))
    op.add_column("tarea", sa.Column("fecha_fin_base", sa.Date(), nullable=True))
    op.execute("UPDATE tarea SET fecha_inicio_base = fecha_inicio, fecha_fin_base = fecha_fin")

    op.add_column(B, sa.Column("descripcion", sa.Text(), nullable=True))
    op.add_column(B, sa.Column("responsable_resolucion", sa.String(150), nullable=True))
    op.add_column(B, sa.Column("fecha_compromiso", sa.Date(), nullable=True))
    op.add_column(B, sa.Column("nota_resolucion", sa.Text(), nullable=True))
    op.add_column(B, sa.Column("automatico", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column(B, sa.Column("horas_impacto", sa.Numeric(8, 2), nullable=True))
    op.add_column(B, sa.Column("id_reportado_por", sa.BigInteger(), nullable=True))
    op.add_column(B, sa.Column("reportado_por_nombre", sa.String(150), nullable=True))
    op.create_foreign_key(
        f"fk_{B}_id_reportado_por_usuario", B, "usuario", ["id_reportado_por"], ["id_usuario"],
        ondelete="SET NULL", onupdate="CASCADE",
    )
    op.alter_column(B, "id_etapa", nullable=True)
    op.drop_constraint("causa_raiz", B, type_="check")
    op.create_check_constraint("causa_raiz", B, _check_causas([*CAUSAS, "Dependencia Interna"]))
    # Una tarea tiene a lo más un bloqueo automático (espera de dependencia) abierto.
    op.create_index(
        "uq_bloqueo_automatico_abierto", B, ["id_tarea"], unique=True,
        postgresql_where=sa.text("automatico AND fecha_fin_bloqueo IS NULL"),
    )

    op.create_table(
        "reprogramacion_tarea",
        sa.Column("id_reprogramacion", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("id_tarea", sa.BigInteger(), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id_actor", sa.BigInteger(), nullable=True),
        sa.Column("actor_nombre", sa.String(150), nullable=False),
        sa.Column("inicio_antes", sa.Date(), nullable=False),
        sa.Column("inicio_despues", sa.Date(), nullable=False),
        sa.Column("fin_antes", sa.Date(), nullable=False),
        sa.Column("fin_despues", sa.Date(), nullable=False),
        sa.Column("dias_habiles", sa.Integer(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("id_bloqueo", sa.BigInteger(), nullable=True),
        sa.Column("es_linea_base", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id_reprogramacion", name="pk_reprogramacion_tarea"),
        sa.ForeignKeyConstraint(["id_tarea"], ["tarea.id_tarea"], name="fk_reprogramacion_tarea_id_tarea_tarea",
                                ondelete="CASCADE", onupdate="CASCADE"),
        sa.ForeignKeyConstraint(["id_actor"], ["usuario.id_usuario"], name="fk_reprogramacion_tarea_id_actor_usuario",
                                ondelete="SET NULL", onupdate="CASCADE"),
        sa.ForeignKeyConstraint(["id_bloqueo"], [f"{B}.id_bloqueo"], name="fk_reprogramacion_tarea_id_bloqueo_bloqueo_interrupcion",
                                ondelete="SET NULL", onupdate="CASCADE"),
    )
    op.create_index("ix_reprogramacion_tarea_id_tarea", "reprogramacion_tarea", ["id_tarea"])


def downgrade() -> None:
    op.drop_table("reprogramacion_tarea")
    op.drop_index("uq_bloqueo_automatico_abierto", B)
    op.execute(f"DELETE FROM {B} WHERE causa_raiz = 'Dependencia Interna' OR id_etapa IS NULL")
    op.drop_constraint("causa_raiz", B, type_="check")
    op.create_check_constraint("causa_raiz", B, _check_causas(CAUSAS))
    op.alter_column(B, "id_etapa", nullable=False)
    op.drop_constraint(f"fk_{B}_id_reportado_por_usuario", B, type_="foreignkey")
    for c in ("reportado_por_nombre", "id_reportado_por", "horas_impacto", "automatico", "nota_resolucion",
              "fecha_compromiso", "responsable_resolucion", "descripcion"):
        op.drop_column(B, c)
    op.drop_column("tarea", "fecha_fin_base")
    op.drop_column("tarea", "fecha_inicio_base")
