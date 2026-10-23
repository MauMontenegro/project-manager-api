from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.departamento import Etiqueta, proyecto_etiqueta
from app.models.enums import DepartamentoProyecto, EstadoProyecto, Semaforo, in_check

if TYPE_CHECKING:
    from app.models.demanda import SolicitudDemanda
    from app.models.operacion import BloqueoInterrupcion, EtapaProyecto, HitoEntregable, RegistroRetrabajo, Tarea
    from app.models.organizacion import Usuario
    from app.models.seguimiento import ActualizacionAvance, CompromisoCliente, RealizacionValor
    from app.models.tablas_uniones import AsignacionRecurso, ProyectoDependencia, ProyectoEmpresaImpactada

CASCADE_CHILD = {"cascade": "all, delete-orphan", "passive_deletes": True}


class Proyecto(Base):
    __tablename__ = "proyecto"
    __table_args__ = (
        in_check("estado_proyecto", EstadoProyecto, "estado_proyecto"),
        in_check("departamento", DepartamentoProyecto, "departamento"),
        # Un conjunto no pertenece a un departamento ni tiene padre; un subproyecto siempre tiene departamento.
        CheckConstraint(
            "NOT es_conjunto OR (departamento IS NULL AND id_proyecto_padre IS NULL AND etapa_actual IS NULL)",
            name="conjunto_valido",
        ),
        CheckConstraint("id_proyecto_padre IS NULL OR departamento IS NOT NULL", name="subproyecto_con_departamento"),
        CheckConstraint("porcentaje_avance BETWEEN 0 AND 100", name="porcentaje_avance_valido"),
        CheckConstraint("horas_presupuestadas IS NULL OR horas_presupuestadas >= 0", name="horas_presupuestadas_no_negativas"),
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
    # Espacio al que pertenece. Nulo en los conjuntos y en proyectos antiguos aún sin asignar.
    departamento: Mapped[str | None] = mapped_column(String(50), index=True)
    # Proyecto conjunto: agrupa un subproyecto por departamento y consolida su avance, fechas y semáforo
    # (conjunto_service). No tiene etapas ni tareas propias.
    es_conjunto: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    id_proyecto_padre: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    # Equipo de trabajo (workspace) al que pertenece; opcional. Un subproyecto toma siempre el de su conjunto.
    id_equipo_trabajo: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("equipo_trabajo.id_equipo_trabajo", ondelete="SET NULL", onupdate="CASCADE"), index=True
    )
    nombre_proyecto: Mapped[str] = mapped_column(String(200))
    problema_oportunidad: Mapped[str] = mapped_column(Text)
    objetivo: Mapped[str] = mapped_column(Text)
    alcance: Mapped[str] = mapped_column(Text)
    fuera_de_alcance: Mapped[str] = mapped_column(Text)
    # Nombre de una de sus etapas (las define el departamento). Nulo en los conjuntos.
    etapa_actual: Mapped[str | None] = mapped_column(String(100), index=True)
    estado_proyecto: Mapped[str] = mapped_column(String(50), default=EstadoProyecto.SIN_INICIAR.value, index=True)
    porcentaje_avance: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), server_default="0.00")
    # Inicio y fin (comprometida o, si no hay, tentativa) delimitan las fechas de las tareas.
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_tentativa: Mapped[date | None] = mapped_column(Date)
    fecha_comprometida: Mapped[date | None] = mapped_column(Date)
    fecha_real_cierre: Mapped[date | None] = mapped_column(Date)
    # Calculado por semaforo_service a partir del avance y las fechas; no se edita a mano.
    # Presupuesto de horas: la suma de las horas de las tareas no puede excederlo (nulo = sin límite).
    # Se calcula con el calendario laboral entre inicio y fin, salvo que se haya fijado a mano.
    horas_presupuestadas: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    horas_presupuestadas_manual: Mapped[bool] = mapped_column(default=False, server_default="false")
    semaforo: Mapped[str] = mapped_column(String(20), default=Semaforo.VERDE.value, index=True)
    semaforo_motivo: Mapped[str | None] = mapped_column(String(200))
    semaforo_fecha: Mapped[date | None] = mapped_column(Date)

    # No mapeado: suma de horas de sus tareas, la llena proyecto_service.obtener_proyecto.
    horas_en_tareas = Decimal("0.00")

    @property
    def fecha_fin(self) -> date | None:
        """Fin del proyecto para delimitar tareas: la comprometida o, si no hay, la tentativa."""
        return self.fecha_comprometida or self.fecha_tentativa

    solicitud: Mapped[SolicitudDemanda | None] = relationship(back_populates="proyecto")
    lider: Mapped[Usuario] = relationship(back_populates="proyectos_liderados")
    padre: Mapped[Proyecto | None] = relationship(back_populates="subproyectos", remote_side="Proyecto.id_proyecto")
    # Se borran explícitamente antes que el conjunto (proyecto_service.eliminar_proyecto); el FK es RESTRICT.
    subproyectos: Mapped[list[Proyecto]] = relationship(
        back_populates="padre", order_by="Proyecto.departamento", passive_deletes="all"
    )
    etiquetas: Mapped[list[Etiqueta]] = relationship(
        secondary=proyecto_etiqueta, order_by=Etiqueta.nombre, passive_deletes=True
    )
    business_case: Mapped[BusinessCase | None] = relationship(back_populates="proyecto", uselist=False, **CASCADE_CHILD)
    evaluacion_financiera: Mapped[EvaluacionFinanciera | None] = relationship(
        back_populates="proyecto", uselist=False, **CASCADE_CHILD
    )
    etapas: Mapped[list[EtapaProyecto]] = relationship(
        back_populates="proyecto", order_by="EtapaProyecto.orden_secuencia", **CASCADE_CHILD
    )
    hitos: Mapped[list[HitoEntregable]] = relationship(back_populates="proyecto", **CASCADE_CHILD)
    tareas: Mapped[list[Tarea]] = relationship(back_populates="proyecto", **CASCADE_CHILD)
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
