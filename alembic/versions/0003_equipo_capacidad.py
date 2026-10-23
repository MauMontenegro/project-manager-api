"""Equipo: tipo de recurso, jerarquía, roles, costo, dedicación, skills con nivel, ausencias y bitácora

- `usuario`: + tipo_recurso, id_jefe, rol, porcentaje_proyectos, costo_hora, proveedor,
  fecha_fin_contrato; `correo` pasa a ser opcional (los activos no tienen).
- Rol inicial: puesto «Director» → Director, «Gerente» → Gerente; el resto, Colaborador.
- `usuario.skills` (arreglo) → catálogo `skill` + `usuario_skill` con nivel (Intermedio por defecto).
- Nuevas tablas `ausencia` y `bitacora`.

Igual que 0002: 0001 crea el esquema desde los modelos vigentes, así que cada paso
comprueba primero el estado real y en una base nueva no hace nada.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK = {"ondelete": "CASCADE", "onupdate": "CASCADE"}


def _en(columna: str, valores: list[str]) -> str:
    return f"{columna} IN ({', '.join(repr(v) for v in valores)})"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columnas = {c["name"] for c in inspector.get_columns("usuario")}

    nuevas = [
        ("tipo_recurso", sa.Column("tipo_recurso", sa.String(20), nullable=False, server_default="Interno")),
        ("rol", sa.Column("rol", sa.String(20), nullable=False, server_default="Colaborador")),
        ("porcentaje_proyectos", sa.Column("porcentaje_proyectos", sa.Numeric(5, 2), nullable=False, server_default="100")),
        ("costo_hora", sa.Column("costo_hora", sa.Numeric(10, 2), nullable=True)),
        ("proveedor", sa.Column("proveedor", sa.String(150), nullable=True)),
        ("fecha_fin_contrato", sa.Column("fecha_fin_contrato", sa.Date(), nullable=True)),
    ]
    for nombre, columna in nuevas:
        if nombre not in columnas:
            op.add_column("usuario", columna)

    if "id_jefe" not in columnas:
        op.add_column("usuario", sa.Column("id_jefe", sa.BigInteger(), nullable=True))
        op.create_foreign_key(
            "fk_usuario_id_jefe_usuario", "usuario", "usuario", ["id_jefe"], ["id_usuario"],
            ondelete="SET NULL", onupdate="CASCADE",
        )
        op.create_index("ix_usuario_id_jefe", "usuario", ["id_jefe"])
        op.create_check_constraint("tipo_recurso", "usuario", _en("tipo_recurso", ["Interno", "Externo", "Activo"]))
        op.create_check_constraint("rol", "usuario", _en("rol", ["Director", "Gerente", "Colaborador"]))
        op.create_check_constraint("porcentaje_proyectos_valido", "usuario", "porcentaje_proyectos BETWEEN 0 AND 100")
        op.create_check_constraint("costo_hora_no_negativo", "usuario", "costo_hora IS NULL OR costo_hora >= 0")
        op.create_check_constraint("sin_autojefe", "usuario", "id_jefe IS NULL OR id_jefe <> id_usuario")
        op.alter_column("usuario", "correo", existing_type=sa.String(150), nullable=True)
        op.execute(
            "UPDATE usuario u SET rol = p.nombre_puesto FROM puesto p "
            "WHERE u.id_puesto = p.id_puesto AND p.nombre_puesto IN ('Director', 'Gerente')"
        )

    if not inspector.has_table("skill"):
        op.create_table(
            "skill",
            sa.Column("id_skill", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("nombre", sa.String(50), nullable=False),
            sa.PrimaryKeyConstraint("id_skill", name="pk_skill"),
            sa.UniqueConstraint("nombre", name="uq_skill_nombre"),
        )
    if not inspector.has_table("usuario_skill"):
        op.create_table(
            "usuario_skill",
            sa.Column("id_usuario", sa.BigInteger(), nullable=False),
            sa.Column("id_skill", sa.BigInteger(), nullable=False),
            sa.Column("nivel", sa.String(20), nullable=False),
            sa.PrimaryKeyConstraint("id_usuario", "id_skill", name="pk_usuario_skill"),
            sa.ForeignKeyConstraint(["id_usuario"], ["usuario.id_usuario"], name="fk_usuario_skill_id_usuario_usuario", **FK),
            sa.ForeignKeyConstraint(["id_skill"], ["skill.id_skill"], name="fk_usuario_skill_id_skill_skill", **FK),
            sa.CheckConstraint(_en("nivel", ["Básico", "Intermedio", "Experto"]), name="ck_usuario_skill_nivel"),
        )
        op.create_index("ix_usuario_skill_id_skill", "usuario_skill", ["id_skill"])

    if "skills" in columnas:
        # Una entrada de catálogo por nombre (sin distinguir mayúsculas), conservando la primera grafía.
        op.execute(
            "INSERT INTO skill (nombre) "
            "SELECT DISTINCT ON (lower(s)) s FROM usuario, unnest(skills) AS s ORDER BY lower(s), s COLLATE \"C\" "
            "ON CONFLICT (nombre) DO NOTHING"
        )
        op.execute(
            "INSERT INTO usuario_skill (id_usuario, id_skill, nivel) "
            "SELECT DISTINCT u.id_usuario, k.id_skill, 'Intermedio' FROM usuario u, unnest(u.skills) AS s "
            "JOIN skill k ON lower(k.nombre) = lower(s) ON CONFLICT DO NOTHING"
        )
        op.drop_column("usuario", "skills")

    if not inspector.has_table("ausencia"):
        op.create_table(
            "ausencia",
            sa.Column("id_ausencia", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("id_usuario", sa.BigInteger(), nullable=False),
            sa.Column("tipo", sa.String(30), nullable=False),
            sa.Column("fecha_inicio", sa.Date(), nullable=False),
            sa.Column("fecha_fin", sa.Date(), nullable=False),
            sa.Column("nota", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id_ausencia", name="pk_ausencia"),
            sa.ForeignKeyConstraint(["id_usuario"], ["usuario.id_usuario"], name="fk_ausencia_id_usuario_usuario", **FK),
            sa.CheckConstraint(
                _en("tipo", ["Vacaciones", "Permiso", "Incapacidad", "Capacitación", "Otro"]), name="ck_ausencia_tipo"
            ),
            sa.CheckConstraint("fecha_fin >= fecha_inicio", name="ck_ausencia_rango_valido"),
        )
        op.create_index("ix_ausencia_id_usuario", "ausencia", ["id_usuario"])

    if not inspector.has_table("bitacora"):
        op.create_table(
            "bitacora",
            sa.Column("id_bitacora", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("id_actor", sa.BigInteger(), nullable=True),
            sa.Column("actor_nombre", sa.String(150), nullable=False),
            sa.Column("entidad", sa.String(50), nullable=False),
            sa.Column("id_entidad", sa.BigInteger(), nullable=False),
            sa.Column("id_usuario_afectado", sa.BigInteger(), nullable=True),
            sa.Column("accion", sa.String(50), nullable=False),
            sa.Column("resumen", sa.Text(), nullable=False),
            sa.Column("cambios", postgresql.JSONB(), nullable=True),
            sa.PrimaryKeyConstraint("id_bitacora", name="pk_bitacora"),
            sa.ForeignKeyConstraint(
                ["id_actor"], ["usuario.id_usuario"], name="fk_bitacora_id_actor_usuario",
                ondelete="SET NULL", onupdate="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["id_usuario_afectado"], ["usuario.id_usuario"], name="fk_bitacora_id_usuario_afectado_usuario", **FK
            ),
        )
        op.create_index("ix_bitacora_fecha", "bitacora", ["fecha"])
        op.create_index("ix_bitacora_id_usuario_afectado", "bitacora", ["id_usuario_afectado"])


def downgrade() -> None:
    # Los niveles de skill, ausencias y bitácora se pierden; los skills vuelven a ser un arreglo.
    op.add_column(
        "usuario",
        sa.Column("skills", postgresql.ARRAY(sa.String(50)), nullable=False, server_default=sa.text("'{}'")),
    )
    op.execute(
        "UPDATE usuario u SET skills = sub.nombres FROM ("
        " SELECT us.id_usuario, array_agg(k.nombre ORDER BY k.nombre)::varchar(50)[] AS nombres"
        " FROM usuario_skill us JOIN skill k USING (id_skill) GROUP BY us.id_usuario) sub"
        " WHERE u.id_usuario = sub.id_usuario"
    )
    op.drop_table("bitacora")
    op.drop_table("ausencia")
    op.drop_table("usuario_skill")
    op.drop_table("skill")
    op.execute("UPDATE usuario SET correo = 'recurso-' || id_usuario || '@sin-correo.local' WHERE correo IS NULL")
    op.alter_column("usuario", "correo", existing_type=sa.String(150), nullable=False)
    for ck in ("tipo_recurso", "rol", "porcentaje_proyectos_valido", "costo_hora_no_negativo", "sin_autojefe"):
        op.execute(f"ALTER TABLE usuario DROP CONSTRAINT IF EXISTS ck_usuario_{ck}")
    op.drop_column("usuario", "id_jefe")
    for col in ("tipo_recurso", "rol", "porcentaje_proyectos", "costo_hora", "proveedor", "fecha_fin_contrato"):
        op.drop_column("usuario", col)
