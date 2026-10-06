"""Esquema inicial: 17 tablas de la plataforma Petroil

Revision ID: 0001
Revises:
Create Date: 2026-10-06
"""
from typing import Sequence, Union

from alembic import op

import app.models  # noqa: F401
from app.core.database import Base

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Línea base: crea el esquema completo a partir de los modelos. Los cambios
    # posteriores deben generarse con `alembic revision --autogenerate`.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
