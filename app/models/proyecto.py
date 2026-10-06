from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import EstadoProyecto, Semaforo, in_check

if TYPE_CHECKING:
    from app.models.demanda import SolicitudDemanda
    from app.models.operacion import BloqueoInterrupcion, EtapaProyecto, HitoEntregable, RegistroRetrabajo
    from app.models.organizacion import Usuario
    from app.models.seguimiento import ActualizacionAvance, CompromisoCliente, RealizacionValor
    from app.models.tablas_uniones import AsignacionRecurso, ProyectoDependencia, ProyectoEmpresaImpactada

CASCADE_CHILD = {"cascade": "all, delete-orphan", "passive_deletes": True}


class Proyecto(Base):
    __tablename__ = "proyecto"
    __table_args__ = (
        in_check("estado_proyecto", EstadoProyecto, "estado_proyecto"),
        in_check("semaforo", Semaforo, "semaforo"),
    )

    id_proyecto: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_solicitud: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("solicitud_demanda.id_solicitud", ondelete="SET NULL", onupdate="CASCADE"),
        unique=True,
    )
    lider_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    nombre_proyecto: Mapped[str] = mapped_column(String(200))
    problema_oportunidad: Mapped[str] = mapped_column(Text)
    objetivo: Mapped[str] = mapped_column(Text)
    alcance: Mapped[str] = mapped_column(Text)
    fuera_de_alcance: Mapped[str] = mapped_column(Text)
    estado_proyecto: Mapped[str] = mapped_column(String(50), default=EstadoProyecto.INICIACION.value, index=True)
    fecha_tentativa: Mapped[date | None] = mapped_column(Date)
    fecha_comprometida: Mapped[date | None] = mapped_column(Date)
    fecha_real_cierre: Mapped[date | None] = mapped_column(Date)
    semaforo: Mapped[str] = mapped_column(String(20), default=Semaforo.VERDE.value, index=True)

    solicitud: Mapped[SolicitudDemanda | None] = relationship(back_populates="proyecto")
    lider: Mapped[Usuario] = relationship(back_populates="proyectos_liderados")
    business_case: Mapped[BusinessCase | None] = relationship(back_populates="proyecto", uselist=False, **CASCADE_CHILD)
    evaluacion_financiera: Mapped[EvaluacionFinanciera | None] = relationship(
        back_populates="proyecto", uselist=False, **CASCADE_CHILD
    )
    etapas: Mapped[list[EtapaProyecto]] = relationship(
        back_populates="proyecto", order_by="EtapaProyecto.orden_secuencia", **CASCADE_CHILD
    )
    hitos: Mapped[list[HitoEntregable]] = relationship(back_populates="proyecto", **CASCADE_CHILD)
    bloqueos: Mapped[list[BloqueoInterrupcion]] = relationship(back_populates="proyecto", **CASCADE_CHILD)
    retrabajos: Mapped[list[RegistroRetrabajo]] = relationship(back_populates="proyecto", **CASCADE_CHILD)
    actualizaciones: Mapped[list[ActualizacionAvance]] = relationship(back_populates="proyecto", **CASCADE_CHILD)
    compromisos: Mapped[list[CompromisoCliente]] = relationship(back_populates="proyecto", **CASCADE_CHILD)
    valores: Mapped[list[RealizacionValor]] = relationship(back_populates="proyecto", **CASCADE_CHILD)
    asignaciones: Mapped[list[AsignacionRecurso]] = relationship(back_populates="proyecto", **CASCADE_CHILD)
    empresas_impactadas: Mapped[list[ProyectoEmpresaImpactada]] = relationship(
        back_populates="proyecto", **CASCADE_CHILD
    )
    dependencias_como_origen: Mapped[list[ProyectoDependencia]] = relationship(
        back_populates="proyecto_origen",
        foreign_keys="ProyectoDependencia.id_proyecto_origen",
        **CASCADE_CHILD,
    )
    dependencias_como_dependiente: Mapped[list[ProyectoDependencia]] = relationship(
        back_populates="proyecto_dependiente",
        foreign_keys="ProyectoDependencia.id_proyecto_dependiente",
        **CASCADE_CHILD,
    )


class BusinessCase(Base):
    __tablename__ = "business_case"

    id_business_case: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_proyecto: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), unique=True
    )
    ahorro_estimado: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"), server_default="0.00")
    costo_evitado_estimado: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0.00"), server_default="0.00"
    )
    capacidad_liberada_horas: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), server_default="0.00"
    )
    incremento_ingreso_estimado: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0.00"), server_default="0.00"
    )
    beneficios_cualitativos: Mapped[str | None] = mapped_column(Text)
    riesgos_cumplimiento: Mapped[str | None] = mapped_column(Text)

    proyecto: Mapped[Proyecto] = relationship(back_populates="business_case")


class EvaluacionFinanciera(Base):
    __tablename__ = "evaluacion_financiera"
    __table_args__ = (CheckConstraint("inversion_total >= 0", name="inversion_no_negativa"),)

    id_evaluacion: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_proyecto: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), unique=True
    )
    costo_desarrollo: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"), server_default="0.00")
    costo_implementacion: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0.00"), server_default="0.00"
    )
    costo_consultoria: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"), server_default="0.00")
    costo_licencias: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"), server_default="0.00")
    costo_infraestructura: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0.00"), server_default="0.00"
    )
    costo_horas_internas: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0.00"), server_default="0.00"
    )
    costo_mantenimiento: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0.00"), server_default="0.00"
    )
    inversion_total: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    beneficio_bruto: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    beneficio_neto: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    roi: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    payback_meses: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    relacion_costo_beneficio: Mapped[Decimal] = mapped_column(Numeric(8, 4))

    proyecto: Mapped[Proyecto] = relationship(back_populates="evaluacion_financiera")
