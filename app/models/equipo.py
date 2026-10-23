from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import NivelSkill, TipoAusencia, in_check

if TYPE_CHECKING:
    from app.models.organizacion import Usuario


class Skill(Base):
    """Catálogo curado de skills; se alimenta al capturar personas y lo depuran Administrador/Gerentes."""

    __tablename__ = "skill"

    id_skill: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True)

    usuarios: Mapped[list[UsuarioSkill]] = relationship(back_populates="skill", passive_deletes=True)


class UsuarioSkill(Base):
    __tablename__ = "usuario_skill"
    __table_args__ = (in_check("nivel", NivelSkill, "nivel"),)

    id_usuario: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True
    )
    id_skill: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skill.id_skill", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True, index=True
    )
    nivel: Mapped[str] = mapped_column(String(20), default=NivelSkill.INTERMEDIO.value)

    usuario: Mapped[Usuario] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship(back_populates="usuarios", lazy="joined")

    @property
    def nombre(self) -> str:
        return self.skill.nombre


class Ausencia(Base):
    __tablename__ = "ausencia"
    __table_args__ = (
        in_check("tipo", TipoAusencia, "tipo"),
        CheckConstraint("fecha_fin >= fecha_inicio", name="rango_valido"),
    )

    id_ausencia: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    tipo: Mapped[str] = mapped_column(String(30))
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date] = mapped_column(Date)
    nota: Mapped[str | None] = mapped_column(Text)

    usuario: Mapped[Usuario] = relationship(back_populates="ausencias")


class Bitacora(Base):
    """Registro de auditoría append-only: quién cambió qué y cuándo."""

    __tablename__ = "bitacora"
    __table_args__ = (Index("ix_bitacora_entidad", "entidad", "id_entidad"),)

    id_bitacora: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    id_actor: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="SET NULL", onupdate="CASCADE")
    )
    actor_nombre: Mapped[str] = mapped_column(String(150))
    entidad: Mapped[str] = mapped_column(String(50))
    id_entidad: Mapped[int] = mapped_column(BigInteger)
    # Persona a la que afecta el cambio (para el historial de su ficha).
    id_usuario_afectado: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    accion: Mapped[str] = mapped_column(String(50))
    resumen: Mapped[str] = mapped_column(Text)
    cambios: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
