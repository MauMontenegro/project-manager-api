from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import CausaRaiz, EstadoEtapa, EstadoHito, NombreEtapa, ResponsableOrigen, in_check
from app.models.proyecto import CASCADE_CHILD

if TYPE_CHECKING:
    from app.models.proyecto import Proyecto
    from app.models.tablas_uniones import AsignacionRecurso


class EtapaProyecto(Base):
    __tablename__ = "etapa_proyecto"
    __table_args__ = (
        in_check("nombre_etapa", NombreEtapa, "nombre_etapa"),
        in_check("estado_etapa", EstadoEtapa, "estado_etapa"),
        CheckConstraint("orden_secuencia > 0", name="orden_positivo"),
        CheckConstraint("horas_estimadas >= 0", name="horas_estimadas_no_negativas"),
        UniqueConstraint("id_proyecto", "orden_secuencia", name="uq_etapa_proyecto_orden"),
    )

    id_etapa: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_proyecto: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    nombre_etapa: Mapped[str] = mapped_column(String(100))
    orden_secuencia: Mapped[int] = mapped_column(Integer)
    horas_estimadas: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    horas_efectivas_reales: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("0.00"), server_default="0.00"
    )
    fecha_inicio_est: Mapped[date | None] = mapped_column(Date)
    fecha_fin_est: Mapped[date | None] = mapped_column(Date)
    estado_etapa: Mapped[str] = mapped_column(String(50), default=EstadoEtapa.PENDIENTE.value)

    proyecto: Mapped[Proyecto] = relationship(back_populates="etapas")
    hitos: Mapped[list[HitoEntregable]] = relationship(back_populates="etapa", **CASCADE_CHILD)
    bloqueos: Mapped[list[BloqueoInterrupcion]] = relationship(back_populates="etapa", **CASCADE_CHILD)
    asignaciones: Mapped[list[AsignacionRecurso]] = relationship(back_populates="etapa", **CASCADE_CHILD)
    retrabajos_origen: Mapped[list[RegistroRetrabajo]] = relationship(
        back_populates="etapa_origen", foreign_keys="RegistroRetrabajo.etapa_origen_id"
    )
    retrabajos_destino: Mapped[list[RegistroRetrabajo]] = relationship(
        back_populates="etapa_destino", foreign_keys="RegistroRetrabajo.etapa_destino_id"
    )


class HitoEntregable(Base):
    __tablename__ = "hito_entregable"
    __table_args__ = (in_check("estado_hito", EstadoHito, "estado_hito"),)

    id_hito: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_proyecto: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    id_etapa: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("etapa_proyecto.id_etapa", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    nombre_entregable: Mapped[str] = mapped_column(String(200))
    fecha_comprometida: Mapped[date] = mapped_column(Date)
    fecha_entrega_real: Mapped[date | None] = mapped_column(Date)
    estado_hito: Mapped[str] = mapped_column(String(50), default=EstadoHito.PENDIENTE.value)

    proyecto: Mapped[Proyecto] = relationship(back_populates="hitos")
    etapa: Mapped[EtapaProyecto] = relationship(back_populates="hitos")


class BloqueoInterrupcion(Base):
    __tablename__ = "bloqueo_interrupcion"
    __table_args__ = (
        in_check("causa_raiz", CausaRaiz, "causa_raiz"),
        in_check("responsable_origen", ResponsableOrigen, "responsable_origen"),
    )

    id_bloqueo: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_proyecto: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    id_etapa: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("etapa_proyecto.id_etapa", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    causa_raiz: Mapped[str] = mapped_column(String(100), index=True)
    responsable_origen: Mapped[str] = mapped_column(String(50))
    fecha_inicio_bloqueo: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    fecha_fin_bloqueo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dias_impacto: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    proyecto: Mapped[Proyecto] = relationship(back_populates="bloqueos")
    etapa: Mapped[EtapaProyecto] = relationship(back_populates="bloqueos")


class RegistroRetrabajo(Base):
    __tablename__ = "registro_retrabajo"
    __table_args__ = (CheckConstraint("horas_adicionales >= 0", name="horas_adicionales_no_negativas"),)

    id_retrabajo: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_proyecto: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    etapa_origen_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("etapa_proyecto.id_etapa", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    etapa_destino_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("etapa_proyecto.id_etapa", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    motivo_regreso: Mapped[str] = mapped_column(Text)
    causa_raiz_requerimiento: Mapped[str] = mapped_column(Text)
    horas_adicionales: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    impacto_dias_fecha: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    proyecto: Mapped[Proyecto] = relationship(back_populates="retrabajos")
    etapa_origen: Mapped[EtapaProyecto] = relationship(
        back_populates="retrabajos_origen", foreign_keys=[etapa_origen_id]
    )
    etapa_destino: Mapped[EtapaProyecto] = relationship(
        back_populates="retrabajos_destino", foreign_keys=[etapa_destino_id]
    )
