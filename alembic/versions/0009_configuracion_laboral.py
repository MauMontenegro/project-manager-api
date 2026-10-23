"""Calendario laboral y presupuesto de horas automático

- Tabla `configuracion_laboral` (fila única) con la jornada por día de la semana
  (L–V 8 h, sábado 5 h, domingo no laboral) y la lista de sábados desactivados.
- `proyecto.horas_presupuestadas_manual`: los presupuestos ya capturados quedan como manuales;
  el resto de proyectos abiertos con inicio y fin se calcula con la jornada por defecto.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-19
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JORNADA_DEFAULT = [{"dia": d, "laborable": d < 6, "horas": 8 if d < 5 else 5 if d == 5 else 0} for d in range(7)]


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("configuracion_laboral"):
        op.create_table(
            "configuracion_laboral",
            sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
            sa.Column("jornada", postgresql.JSONB(), nullable=False),
            sa.Column("sabados_inactivos", postgresql.ARRAY(sa.Date()), nullable=False, server_default="{}"),
            sa.PrimaryKeyConstraint("id", name="pk_configuracion_laboral"),
            sa.CheckConstraint("id = 1", name="fila_unica"),
        )
    if "jornada" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("configuracion_laboral")}:
        op.execute(
            sa.text("INSERT INTO configuracion_laboral (id, jornada) VALUES (1, CAST(:j AS jsonb)) ON CONFLICT (id) DO NOTHING")
            .bindparams(j=json.dumps(JORNADA_DEFAULT))
        )
    else:  # base nueva: 0001 ya creó la tabla con el esquema de 0010 (valores por defecto en columnas)
        op.execute("INSERT INTO configuracion_laboral (id) VALUES (1) ON CONFLICT (id) DO NOTHING")

    if "horas_presupuestadas_manual" not in {c["name"] for c in inspector.get_columns("proyecto")}:
        op.add_column(
            "proyecto",
            sa.Column("horas_presupuestadas_manual", sa.Boolean(), nullable=False, server_default="false"),
        )
        op.execute("UPDATE proyecto SET horas_presupuestadas_manual = true WHERE horas_presupuestadas IS NOT NULL")
        # Mismo cálculo que configuracion_service con la jornada por defecto (isodow: 1 = lunes … 7 = domingo).
        op.execute(
            "UPDATE proyecto p SET horas_presupuestadas = ("
            " SELECT COALESCE(SUM(CASE WHEN EXTRACT(ISODOW FROM d) <= 5 THEN 8"
            "                          WHEN EXTRACT(ISODOW FROM d) = 6 THEN 5 ELSE 0 END), 0)"
            " FROM generate_series(p.fecha_inicio, COALESCE(p.fecha_comprometida, p.fecha_tentativa), interval '1 day') d)"
            " WHERE NOT p.horas_presupuestadas_manual AND p.fecha_inicio IS NOT NULL"
            " AND COALESCE(p.fecha_comprometida, p.fecha_tentativa) >= p.fecha_inicio"
            " AND p.estado_proyecto NOT IN ('Completado', 'Cancelado')"
        )


def downgrade() -> None:
    op.drop_column("proyecto", "horas_presupuestadas_manual")
    op.drop_table("configuracion_laboral")
