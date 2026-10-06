from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import EstadoCompromiso, in_check

if TYPE_CHECKING:
    from app.models.organizacion import Area, Usuario
    from app.models.proyecto import Proyecto


class ActualizacionAvance(Base):
    __tablename__ = "actualizacion_avance"
    __table_args__ = (CheckConstraint("porcentaje_avance BETWEEN 0 AND 100", name="porcentaje_valido"),)

    id_actualizacion: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_proyecto: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    id_usuario_registra: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    fecha_registro: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    porcentaje_avance: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    resumen_avance: Mapped[str] = mapped_column(Text)
    proximo_hito: Mapped[str | None] = mapped_column(String(200))
    riesgo_detectado: Mapped[str | None] = mapped_column(Text)

    proyecto: Mapped[Proyecto] = relationship(back_populates="actualizaciones")
    usuario_registra: Mapped[Usuario] = relationship(back_populates="actualizaciones")


class CompromisoCliente(Base):
    __tablename__ = "compromiso_cliente"
    __table_args__ = (in_check("estado_compromiso", EstadoCompromiso, "estado_compromiso"),)

    id_compromiso: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_proyecto: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    id_area_cliente: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("area.id_area", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    descripcion_actividad: Mapped[str] = mapped_column(Text)
    fecha_limite_compromiso: Mapped[date] = mapped_column(Date)
    fecha_cumplimiento_real: Mapped[date | None] = mapped_column(Date)
    estado_compromiso: Mapped[str] = mapped_column(String(50), default=EstadoCompromiso.PENDIENTE.value)

    proyecto: Mapped[Proyecto] = relationship(back_populates="compromisos")
    area_cliente: Mapped[Area] = relationship(back_populates="compromisos_cliente")


class RealizacionValor(Base):
    __tablename__ = "realizacion_valor"

    id_valor: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_proyecto: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    impacto_estimado: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    impacto_comprometido: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    impacto_aprobado: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    impacto_realizado: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    fecha_validacion: Mapped[date] = mapped_column(Date)
    observaciones: Mapped[str | None] = mapped_column(Text)

    proyecto: Mapped[Proyecto] = relationship(back_populates="valores")
