"""Configuración laboral simplificada: horas L–V, horas sábado y días desactivados

Sustituye la jornada por día de la semana y la lista de sábados por:
`horas_entre_semana`, `horas_sabado` (0 = no laboral; el domingo nunca cuenta) y `dias_inactivos`
(cualquier fecha). Se conservan los valores vigentes: las horas del lunes, las del sábado (0 si no era
laborable) y los sábados desactivados.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-19
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

T = "configuracion_laboral"


def upgrade() -> None:
    columnas = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(T)}
    if "horas_entre_semana" not in columnas:
        op.add_column(T, sa.Column("horas_entre_semana", sa.Numeric(4, 2), nullable=False, server_default="8"))
        op.add_column(T, sa.Column("horas_sabado", sa.Numeric(4, 2), nullable=False, server_default="5"))
        op.add_column(T, sa.Column("dias_inactivos", postgresql.ARRAY(sa.Date()), nullable=False, server_default="{}"))
        op.create_check_constraint("horas_entre_semana_validas", T, "horas_entre_semana BETWEEN 0 AND 24")
        op.create_check_constraint("horas_sabado_validas", T, "horas_sabado BETWEEN 0 AND 24")
    if "jornada" in columnas:
        op.execute(
            f"UPDATE {T} SET"
            " horas_entre_semana = (jornada -> 0 ->> 'horas')::numeric,"
            " horas_sabado = CASE WHEN (jornada -> 5 ->> 'laborable')::boolean THEN (jornada -> 5 ->> 'horas')::numeric ELSE 0 END,"
            " dias_inactivos = sabados_inactivos"
        )
        op.drop_column(T, "jornada")
        op.drop_column(T, "sabados_inactivos")


def downgrade() -> None:
    op.add_column(T, sa.Column("jornada", postgresql.JSONB(), nullable=True))
    op.add_column(T, sa.Column("sabados_inactivos", postgresql.ARRAY(sa.Date()), nullable=False, server_default="{}"))
    bind = op.get_bind()
    for horas_ls, horas_s, dias in bind.execute(sa.text(f"SELECT horas_entre_semana, horas_sabado, dias_inactivos FROM {T}")):
        jornada = [{"dia": d, "laborable": d < 5 or (d == 5 and horas_s > 0),
                    "horas": float(horas_ls if d < 5 else horas_s if d == 5 else 0)} for d in range(7)]
        bind.execute(
            sa.text(f"UPDATE {T} SET jornada = CAST(:j AS jsonb), sabados_inactivos = :s").bindparams(
                j=json.dumps(jornada), s=[d for d in dias if d.weekday() == 5]
            )
        )
    op.alter_column(T, "jornada", nullable=False)
    for col in ("dias_inactivos", "horas_sabado", "horas_entre_semana"):
        op.drop_column(T, col)  # arrastra sus CHECK
