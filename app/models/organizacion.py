from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import Departamento, RolSistema, TipoRecurso, in_check

if TYPE_CHECKING:
    from app.models.demanda import SolicitudDemanda
    from app.models.equipo import Ausencia, UsuarioSkill
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
    solicitudes: Mapped[list[SolicitudDemanda]] = relationship(back_populates="area")
    compromisos_cliente: Mapped[list[CompromisoCliente]] = relationship(back_populates="area_cliente")


class Puesto(Base):
    """Catálogo administrable de puestos de la DTI (Director, Gerente, Analista, ...)."""

    __tablename__ = "puesto"

    id_puesto: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nombre_puesto: Mapped[str] = mapped_column(String(100), unique=True)

    usuarios: Mapped[list[Usuario]] = relationship(back_populates="puesto")


class Usuario(Base):
    """Recurso del Equipo DTI: persona interna, externa (proveedor) o activo no humano."""

    __tablename__ = "usuario"
    __table_args__ = (
        in_check("departamento", Departamento, "departamento"),
        in_check("tipo_recurso", TipoRecurso, "tipo_recurso"),
        in_check("rol", RolSistema, "rol"),
        CheckConstraint("capacidad_horas_semanales >= 0", name="capacidad_no_negativa"),
        CheckConstraint("porcentaje_proyectos BETWEEN 0 AND 100", name="porcentaje_proyectos_valido"),
        CheckConstraint("costo_hora IS NULL OR costo_hora >= 0", name="costo_hora_no_negativo"),
        CheckConstraint("id_jefe IS NULL OR id_jefe <> id_usuario", name="sin_autojefe"),
    )

    id_usuario: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tipo_recurso: Mapped[str] = mapped_column(
        String(20), default=TipoRecurso.INTERNO.value, server_default=TipoRecurso.INTERNO.value
    )
    # Nulos solo en registros previos a la migración 0002 (y puesto/correo en activos); la API los valida.
    id_puesto: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("puesto.id_puesto", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    departamento: Mapped[str | None] = mapped_column(String(50))
    id_jefe: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="SET NULL", onupdate="CASCADE"), index=True
    )
    rol: Mapped[str] = mapped_column(
        String(20), default=RolSistema.USUARIO.value, server_default=RolSistema.USUARIO.value
    )
    nombre: Mapped[str] = mapped_column(String(150))
    correo: Mapped[str | None] = mapped_column(String(150), unique=True)
    capacidad_horas_semanales: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    # Parte de la capacidad disponible para proyectos; el resto es operación/soporte.
    porcentaje_proyectos: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(100), server_default="100")
    costo_hora: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    proveedor: Mapped[str | None] = mapped_column(String(150))
    fecha_fin_contrato: Mapped[date | None] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # Inicio de sesión con contraseña (hash scrypt; nunca se expone). Temporal: se exige cambiarla al entrar.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    password_temporal: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    password_actualizada: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def tiene_password(self) -> bool:
        return self.password_hash is not None

    puesto: Mapped[Puesto | None] = relationship(back_populates="usuarios")
    skills: Mapped[list[UsuarioSkill]] = relationship(
        back_populates="usuario", lazy="selectin", cascade="all, delete-orphan", passive_deletes=True
    )
    ausencias: Mapped[list[Ausencia]] = relationship(back_populates="usuario", passive_deletes=True)
    solicitudes: Mapped[list[SolicitudDemanda]] = relationship(back_populates="usuario_solicitante")
    proyectos_liderados: Mapped[list[Proyecto]] = relationship(back_populates="lider")
    actualizaciones: Mapped[list[ActualizacionAvance]] = relationship(back_populates="usuario_registra")
    asignaciones: Mapped[list[AsignacionRecurso]] = relationship(back_populates="usuario")
