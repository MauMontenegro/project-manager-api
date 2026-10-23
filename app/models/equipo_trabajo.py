"""Equipos de trabajo (workspaces): agrupan personas de cualquier departamento y los proyectos de una línea de
negocio o cliente interno (p. ej. Servicios Corporativos, Combustibles). Solo organizan (filtros, métricas);
los permisos siguen por rol y departamento."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.organizacion import Usuario

# Una persona puede estar en varios equipos de trabajo.
equipo_trabajo_miembro = Table(
    "equipo_trabajo_miembro",
    Base.metadata,
    Column("id_equipo_trabajo", BigInteger, ForeignKey("equipo_trabajo.id_equipo_trabajo", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True),
    Column("id_usuario", BigInteger, ForeignKey("usuario.id_usuario", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True, index=True),
)


class EquipoTrabajo(Base):
    __tablename__ = "equipo_trabajo"
    __table_args__ = (CheckConstraint("color ~ '^#[0-9a-fA-F]{6}$'", name="color_hex"),)

    id_equipo_trabajo: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(String(7))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    miembros: Mapped[list[Usuario]] = relationship(secondary=equipo_trabajo_miembro, order_by="Usuario.nombre", passive_deletes=True)


Index("uq_equipo_trabajo_nombre", func.lower(EquipoTrabajo.nombre), unique=True)
