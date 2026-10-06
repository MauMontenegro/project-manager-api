from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import PerfilTecnico, in_check

if TYPE_CHECKING:
    from app.models.demanda import SolicitudDemanda
    from app.models.proyecto import Proyecto
    from app.models.seguimiento import ActualizacionAvance, CompromisoCliente
    from app.models.tablas_uniones import AsignacionRecurso, ProyectoEmpresaImpactada


class Empresa(Base):
    __tablename__ = "empresa"

    id_empresa: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nombre_empresa: Mapped[str] = mapped_column(String(150), unique=True)
    division: Mapped[str] = mapped_column(String(100))
    grupo: Mapped[str] = mapped_column(String(100))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    areas: Mapped[list[Area]] = relationship(back_populates="empresa")
    solicitudes: Mapped[list[SolicitudDemanda]] = relationship(back_populates="empresa")
    proyectos_impactados: Mapped[list[ProyectoEmpresaImpactada]] = relationship(back_populates="empresa")


class Area(Base):
    __tablename__ = "area"

    id_area: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_empresa: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("empresa.id_empresa", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    nombre_area: Mapped[str] = mapped_column(String(150))
    codigo_area: Mapped[str] = mapped_column(String(50), unique=True)

    empresa: Mapped[Empresa] = relationship(back_populates="areas")
    usuarios: Mapped[list[Usuario]] = relationship(back_populates="area")
    solicitudes: Mapped[list[SolicitudDemanda]] = relationship(back_populates="area")
    compromisos_cliente: Mapped[list[CompromisoCliente]] = relationship(back_populates="area_cliente")


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (
        in_check("perfil_tecnico", PerfilTecnico, "perfil_tecnico"),
        CheckConstraint("capacidad_horas_semanales >= 0", name="capacidad_no_negativa"),
    )

    id_usuario: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_area: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("area.id_area", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    nombre: Mapped[str] = mapped_column(String(150))
    correo: Mapped[str] = mapped_column(String(150), unique=True)
    perfil_tecnico: Mapped[str] = mapped_column(String(100))
    capacidad_horas_semanales: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))

    area: Mapped[Area] = relationship(back_populates="usuarios")
    solicitudes: Mapped[list[SolicitudDemanda]] = relationship(back_populates="usuario_solicitante")
    proyectos_liderados: Mapped[list[Proyecto]] = relationship(back_populates="lider")
    actualizaciones: Mapped[list[ActualizacionAvance]] = relationship(back_populates="usuario_registra")
    asignaciones: Mapped[list[AsignacionRecurso]] = relationship(back_populates="usuario")
