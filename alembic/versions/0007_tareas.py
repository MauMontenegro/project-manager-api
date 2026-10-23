"""Tareas por etapa y avance calculado (20 % por etapa)

- Nueva tabla `tarea` (kanban: Pendiente, En progreso, En revisión, Finalizado).
- El avance del proyecto pasa a calcularse con las tareas: cada etapa vale 20 %. Como aún no hay
  tareas, cada proyecto queda con el 20 % de cada etapa ya pasada (100 % si está Completado), y
  su semáforo se marca para recalcularse en la próxima consulta.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ETAPAS = ["Análisis y Viabilidad", "Diseño y Planificación", "Construcción y Ejecución", "Pruebas y Validación", "Despliegue y Cierre"]
ESTADOS_TAREA = ["Pendiente", "En progreso", "En revisión", "Finalizado"]
FK = {"ondelete": "CASCADE", "onupdate": "CASCADE"}


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("tarea"):
        op.create_table(
            "tarea",
            sa.Column("id_tarea", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("id_proyecto", sa.BigInteger(), nullable=False),
            sa.Column("id_etapa", sa.BigInteger(), nullable=False),
            sa.Column("id_usuario", sa.BigInteger(), nullable=False),
            sa.Column("titulo", sa.String(200), nullable=False),
            sa.Column("descripcion", sa.Text(), nullable=True),
            sa.Column("horas_asignadas", sa.Numeric(8, 2), nullable=False),
            sa.Column("fecha_inicio", sa.Date(), nullable=True),
            sa.Column("fecha_fin", sa.Date(), nullable=True),
            sa.Column("estado", sa.String(20), nullable=False),
            sa.Column("fecha_creacion", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("fecha_finalizacion", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id_tarea", name="pk_tarea"),
            sa.ForeignKeyConstraint(["id_proyecto"], ["proyecto.id_proyecto"], name="fk_tarea_id_proyecto_proyecto", **FK),
            sa.ForeignKeyConstraint(["id_etapa"], ["etapa_proyecto.id_etapa"], name="fk_tarea_id_etapa_etapa_proyecto", **FK),
            sa.ForeignKeyConstraint(
                ["id_usuario"], ["usuario.id_usuario"], name="fk_tarea_id_usuario_usuario",
                ondelete="RESTRICT", onupdate="CASCADE",
            ),
            sa.CheckConstraint(
                f"estado IN ({', '.join(repr(e) for e in ESTADOS_TAREA)})", name="estado"
            ),
            sa.CheckConstraint("horas_asignadas >= 0", name="horas_no_negativas"),
            sa.CheckConstraint(
                "fecha_fin IS NULL OR fecha_inicio IS NULL OR fecha_fin >= fecha_inicio", name="fechas_validas"
            ),
        )
        for columna in ("id_proyecto", "id_etapa", "id_usuario", "estado"):
            op.create_index(f"ix_tarea_{columna}", "tarea", [columna])

    casos = " ".join(f"WHEN '{nombre}' THEN {20 * i}" for i, nombre in enumerate(ETAPAS))
    op.execute(
        "UPDATE proyecto SET semaforo_fecha = NULL, porcentaje_avance = CASE"
        " WHEN estado_proyecto = 'Completado' THEN 100"
        f" ELSE CASE etapa_actual {casos} ELSE 0 END END"
    )


def downgrade() -> None:
    op.drop_table("tarea")
