"""Equipo: perfil técnico -> puesto (catálogo), área -> departamento DTI, skills

- Crea el catálogo `puesto` y lo siembra con los puestos base.
- `usuario.perfil_tecnico` se elimina; su valor se conserva como skill
  (salvo 'Líder' y 'Cliente', que no son especialidades).
- `usuario.id_area` se sustituye por `usuario.departamento`
  (Dirección, Infraestructura, Procesos, Desarrollo de Software).
- Las personas existentes quedan con puesto y departamento nulos hasta editarlas.

Como 0001 crea el esquema desde los modelos actuales, en una base nueva esta
revisión no tiene nada que hacer: cada paso comprueba primero el estado real.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PUESTOS_BASE = [
    "Director", "Gerente", "Coordinador", "Líder Técnico", "Especialista", "Analista", "Desarrollador", "Técnico",
]
DEPARTAMENTOS = ["Dirección", "Infraestructura", "Procesos", "Desarrollo de Software"]


def _columnas(tabla: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("puesto"):
        op.create_table(
            "puesto",
            sa.Column("id_puesto", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("nombre_puesto", sa.String(100), nullable=False),
            sa.PrimaryKeyConstraint("id_puesto", name="pk_puesto"),
            sa.UniqueConstraint("nombre_puesto", name="uq_puesto_nombre_puesto"),
        )
    puesto = sa.table("puesto", sa.column("nombre_puesto", sa.String))
    existentes = set(op.get_bind().scalars(sa.select(puesto.c.nombre_puesto)))
    nuevos = [{"nombre_puesto": n} for n in PUESTOS_BASE if n not in existentes]
    if nuevos:
        op.bulk_insert(puesto, nuevos)

    columnas = _columnas("usuario")
    if "id_puesto" not in columnas:
        op.add_column("usuario", sa.Column("id_puesto", sa.BigInteger(), nullable=True))
        op.create_foreign_key(
            "fk_usuario_id_puesto_puesto", "usuario", "puesto", ["id_puesto"], ["id_puesto"],
            ondelete="RESTRICT", onupdate="CASCADE",
        )
        op.create_index("ix_usuario_id_puesto", "usuario", ["id_puesto"])
    if "departamento" not in columnas:
        op.add_column("usuario", sa.Column("departamento", sa.String(50), nullable=True))
        valores = ", ".join(f"'{d}'" for d in DEPARTAMENTOS)
        op.create_check_constraint("departamento", "usuario", f"departamento IN ({valores})")
    if "skills" not in columnas:
        op.add_column(
            "usuario",
            sa.Column("skills", postgresql.ARRAY(sa.String(50)), nullable=False, server_default=sa.text("'{}'")),
        )

    if "perfil_tecnico" in columnas:
        op.execute(
            "UPDATE usuario SET skills = ARRAY[perfil_tecnico]::varchar(50)[] "
            "WHERE perfil_tecnico NOT IN ('Líder', 'Cliente')"
        )
        op.execute("ALTER TABLE usuario DROP CONSTRAINT IF EXISTS ck_usuario_perfil_tecnico")
        op.drop_column("usuario", "perfil_tecnico")
    if "id_area" in columnas:
        # Elimina también su FK e índice.
        op.drop_column("usuario", "id_area")


def downgrade() -> None:
    # Restaura la forma de las columnas; puesto, departamento y skills se pierden
    # y el área/perfil originales no pueden recuperarse.
    op.add_column("usuario", sa.Column("perfil_tecnico", sa.String(100), nullable=True))
    op.add_column("usuario", sa.Column("id_area", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_usuario_id_area_area", "usuario", "area", ["id_area"], ["id_area"],
        ondelete="RESTRICT", onupdate="CASCADE",
    )
    op.create_index("ix_usuario_id_area", "usuario", ["id_area"])
    op.drop_column("usuario", "skills")
    op.execute("ALTER TABLE usuario DROP CONSTRAINT IF EXISTS ck_usuario_departamento")
    op.drop_column("usuario", "departamento")
    op.drop_column("usuario", "id_puesto")
    op.drop_table("puesto")
