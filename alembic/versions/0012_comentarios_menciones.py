"""Comentarios con @menciones en tareas y su trazabilidad

- `comentario_tarea` y `mencion` (cada mención es una notificación con su estado de lectura).
- Índice `ix_bitacora_entidad` (entidad, id_entidad) para la línea de tiempo de cada tarea.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CASCADE = {"ondelete": "CASCADE", "onupdate": "CASCADE"}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("comentario_tarea"):
        op.create_table(
            "comentario_tarea",
            sa.Column("id_comentario", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("id_tarea", sa.BigInteger(), nullable=False),
            sa.Column("id_autor", sa.BigInteger(), nullable=True),
            sa.Column("autor_nombre", sa.String(150), nullable=False),
            sa.Column("texto", sa.Text(), nullable=False),
            sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id_comentario", name="pk_comentario_tarea"),
            sa.ForeignKeyConstraint(["id_tarea"], ["tarea.id_tarea"], name="fk_comentario_tarea_id_tarea_tarea", **CASCADE),
            sa.ForeignKeyConstraint(
                ["id_autor"], ["usuario.id_usuario"], name="fk_comentario_tarea_id_autor_usuario",
                ondelete="SET NULL", onupdate="CASCADE",
            ),
        )
        op.create_index("ix_comentario_tarea_id_tarea", "comentario_tarea", ["id_tarea"])
        op.create_index("ix_comentario_tarea_fecha", "comentario_tarea", ["fecha"])
    if not inspector.has_table("mencion"):
        op.create_table(
            "mencion",
            sa.Column("id_mencion", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("id_comentario", sa.BigInteger(), nullable=False),
            sa.Column("id_usuario", sa.BigInteger(), nullable=False),
            sa.Column("leida", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("fecha_leida", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id_mencion", name="pk_mencion"),
            sa.ForeignKeyConstraint(
                ["id_comentario"], ["comentario_tarea.id_comentario"], name="fk_mencion_id_comentario_comentario_tarea", **CASCADE
            ),
            sa.ForeignKeyConstraint(["id_usuario"], ["usuario.id_usuario"], name="fk_mencion_id_usuario_usuario", **CASCADE),
            sa.UniqueConstraint("id_comentario", "id_usuario", name="uq_mencion_comentario_usuario"),
        )
        op.create_index("ix_mencion_id_comentario", "mencion", ["id_comentario"])
        op.create_index("ix_mencion_id_usuario", "mencion", ["id_usuario"])
    if "ix_bitacora_entidad" not in {i["name"] for i in inspector.get_indexes("bitacora")}:
        op.create_index("ix_bitacora_entidad", "bitacora", ["entidad", "id_entidad"])


def downgrade() -> None:
    op.drop_index("ix_bitacora_entidad", table_name="bitacora")
    op.drop_table("mencion")
    op.drop_table("comentario_tarea")
