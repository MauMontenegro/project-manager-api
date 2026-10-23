from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func,
    select, text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from app.core.database import Base
from app.models.enums import CausaRaiz, EstadoEtapa, EstadoHito, EstadoTarea, ResponsableOrigen, in_check
from app.models.proyecto import CASCADE_CHILD

if TYPE_CHECKING:
    from app.models.organizacion import Usuario
    from app.models.recurrente import TareaRecurrente
    from app.models.proyecto import Proyecto
    from app.models.tablas_uniones import AsignacionRecurso


class EtapaProyecto(Base):
    __tablename__ = "etapa_proyecto"
    __table_args__ = (
        in_check("estado_etapa", EstadoEtapa, "estado_etapa"),
        CheckConstraint("orden_secuencia > 0", name="orden_positivo"),
        CheckConstraint("horas_estimadas >= 0", name="horas_estimadas_no_negativas"),
        UniqueConstraint("id_proyecto", "orden_secuencia", name="uq_etapa_proyecto_orden"),
    )

    id_etapa: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_proyecto: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    # Copiados de la plantilla del departamento al crear el proyecto.
    nombre_etapa: Mapped[str] = mapped_column(String(100))
    orden_secuencia: Mapped[int] = mapped_column(Integer)
    descripcion: Mapped[str | None] = mapped_column(Text)
    estados_permitidos: Mapped[list[str]] = mapped_column(ARRAY(String(50)))
    horas_estimadas: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    horas_efectivas_reales: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), default=Decimal("0.00"), server_default="0.00"
    )
    fecha_inicio_est: Mapped[date | None] = mapped_column(Date)
    fecha_fin_est: Mapped[date | None] = mapped_column(Date)
    estado_etapa: Mapped[str] = mapped_column(String(50), default=EstadoEtapa.SIN_INICIAR.value)

    proyecto: Mapped[Proyecto] = relationship(back_populates="etapas")
    hitos: Mapped[list[HitoEntregable]] = relationship(back_populates="etapa", **CASCADE_CHILD)
    bloqueos: Mapped[list[BloqueoInterrupcion]] = relationship(back_populates="etapa", **CASCADE_CHILD)
    asignaciones: Mapped[list[AsignacionRecurso]] = relationship(back_populates="etapa", **CASCADE_CHILD)
    tareas: Mapped[list[Tarea]] = relationship(back_populates="etapa", **CASCADE_CHILD)
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
    """Periodo en que una tarea (o, sin tarea, una etapa) no pudo avanzar. Lo reporta la persona asignada o quien
    gestiona el proyecto; los `automatico` los abre y cierra el sistema mientras la tarea espera a sus dependencias
    (ver bloqueo_service). Su duración se mide en días y horas hábiles del calendario laboral."""

    __tablename__ = "bloqueo_interrupcion"
    __table_args__ = (
        in_check("causa_raiz", CausaRaiz, "causa_raiz"),
        in_check("responsable_origen", ResponsableOrigen, "responsable_origen"),
        Index(
            "uq_bloqueo_automatico_abierto", "id_tarea", unique=True,
            postgresql_where=text("automatico AND fecha_fin_bloqueo IS NULL"),
        ),
    )

    id_bloqueo: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_proyecto: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    # Nula solo en tareas generales de un proyecto conjunto (no tiene etapas).
    id_etapa: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("etapa_proyecto.id_etapa", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    # Actividad (tarea) de la etapa afectada, si la hay. Al borrar la tarea, el bloqueo queda en la etapa.
    id_tarea: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tarea.id_tarea", ondelete="SET NULL", onupdate="CASCADE"), index=True
    )
    causa_raiz: Mapped[str] = mapped_column(String(100), index=True)
    responsable_origen: Mapped[str] = mapped_column(String(50))
    fecha_inicio_bloqueo: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    fecha_fin_bloqueo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Al cerrarlo: duración en días y horas hábiles (calendario laboral).
    dias_impacto: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    horas_impacto: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    descripcion: Mapped[str | None] = mapped_column(Text)
    # Quién debe destrabarlo (persona, área o empresa) y para cuándo se comprometió.
    responsable_resolucion: Mapped[str | None] = mapped_column(String(150))
    fecha_compromiso: Mapped[date | None] = mapped_column(Date)
    nota_resolucion: Mapped[str | None] = mapped_column(Text)
    automatico: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    id_reportado_por: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="SET NULL", onupdate="CASCADE")
    )
    reportado_por_nombre: Mapped[str | None] = mapped_column(String(150))

    proyecto: Mapped[Proyecto] = relationship(back_populates="bloqueos")
    etapa: Mapped[EtapaProyecto | None] = relationship(back_populates="bloqueos")


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


class Tarea(Base):
    """Trabajo concreto asignado a una persona. Es de una etapa de proyecto (las `Finalizado` definen el
    avance de su etapa y con él el del proyecto), propia de un proyecto conjunto (sin etapa: coordina a sus
    subproyectos y no cuenta en su avance) o la tarea de un periodo de una tarea recurrente (operación del
    día a día, ver recurrente_service)."""

    __tablename__ = "tarea"
    __table_args__ = (
        in_check("estado", EstadoTarea, "estado"),
        CheckConstraint("horas_asignadas >= 0", name="horas_no_negativas"),
        CheckConstraint("horas_reales IS NULL OR horas_reales >= 0", name="horas_reales_no_negativas"),
        CheckConstraint("fecha_fin IS NULL OR fecha_inicio IS NULL OR fecha_fin >= fecha_inicio", name="fechas_validas"),
        CheckConstraint(
            "(id_recurrente IS NULL AND id_proyecto IS NOT NULL AND periodo IS NULL)"
            " OR (id_recurrente IS NOT NULL AND id_proyecto IS NULL AND id_etapa IS NULL AND periodo IS NOT NULL)",
            name="origen_valido",
        ),
        UniqueConstraint("id_recurrente", "periodo", name="uq_tarea_recurrente_periodo"),
    )

    id_tarea: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # De proyecto: proyecto y etapa (sin etapa en un conjunto). Recurrente: la plantilla y el periodo (primer día del día/semana/mes).
    id_proyecto: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    id_etapa: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("etapa_proyecto.id_etapa", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    id_recurrente: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tarea_recurrente.id_recurrente", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    periodo: Mapped[date | None] = mapped_column(Date)
    id_usuario: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    titulo: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text)
    horas_asignadas: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    # Horas que realmente tomó; las registra la persona (o quien gestiona) al finalizarla.
    horas_reales: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    # Obligatorias: con ellas se reparte la carga semanal de la persona (ver capacidad_service).
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date] = mapped_column(Date)
    # Línea base (plan original): se fija al crear la tarea; contra ella se mide el desfase.
    fecha_inicio_base: Mapped[date | None] = mapped_column(Date)
    fecha_fin_base: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoTarea.PENDIENTE.value, index=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fecha_finalizacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    proyecto: Mapped[Proyecto | None] = relationship(back_populates="tareas")
    etapa: Mapped[EtapaProyecto | None] = relationship(back_populates="tareas")
    recurrente: Mapped[TareaRecurrente | None] = relationship(back_populates="tareas")
    usuario: Mapped[Usuario] = relationship()
    comentarios: Mapped[list[ComentarioTarea]] = relationship(back_populates="tarea", **CASCADE_CHILD)
    bloqueos: Mapped[list[BloqueoInterrupcion]] = relationship(
        primaryjoin="Tarea.id_tarea == foreign(BloqueoInterrupcion.id_tarea)", viewonly=True,
        order_by="BloqueoInterrupcion.fecha_inicio_bloqueo",
    )
    reprogramaciones: Mapped[list[ReprogramacionTarea]] = relationship(
        back_populates="tarea", order_by="ReprogramacionTarea.fecha", **CASCADE_CHILD
    )
    # Tareas que deben estar `Finalizado` antes de que esta salga de `Pendiente`, y las que esperan a esta.
    dependencias: Mapped[list[Tarea]] = relationship(
        secondary="tarea_dependencia", primaryjoin="Tarea.id_tarea == TareaDependencia.id_tarea",
        secondaryjoin="Tarea.id_tarea == TareaDependencia.id_dependencia", back_populates="dependientes",
        order_by="Tarea.id_tarea", passive_deletes=True,
    )
    dependientes: Mapped[list[Tarea]] = relationship(
        secondary="tarea_dependencia", primaryjoin="Tarea.id_tarea == TareaDependencia.id_dependencia",
        secondaryjoin="Tarea.id_tarea == TareaDependencia.id_tarea", back_populates="dependencias",
        order_by="Tarea.id_tarea", passive_deletes=True,
    )


class TareaDependencia(Base):
    """`id_tarea` no puede salir de `Pendiente` hasta que `id_dependencia` esté `Finalizado`.
    Ambas del mismo proyecto o del mismo conjunto (el conjunto y sus subproyectos), sin ciclos (lo valida
    tarea_service)."""

    __tablename__ = "tarea_dependencia"
    __table_args__ = (CheckConstraint("id_tarea <> id_dependencia", name="sin_autodependencia"),)

    id_tarea: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tarea.id_tarea", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True
    )
    id_dependencia: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tarea.id_tarea", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True, index=True
    )



class ReprogramacionTarea(Base):
    """Cambio de fechas de una tarea de proyecto, o nueva línea base (`es_linea_base`). `dias_habiles`: cuánto se
    movió la fecha límite (positivo = se retrasó). Retrasarla exige motivo; puede atribuirse a un bloqueo."""

    __tablename__ = "reprogramacion_tarea"

    id_reprogramacion: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_tarea: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tarea.id_tarea", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    id_actor: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="SET NULL", onupdate="CASCADE")
    )
    actor_nombre: Mapped[str] = mapped_column(String(150))
    inicio_antes: Mapped[date] = mapped_column(Date)
    inicio_despues: Mapped[date] = mapped_column(Date)
    fin_antes: Mapped[date] = mapped_column(Date)
    fin_despues: Mapped[date] = mapped_column(Date)
    dias_habiles: Mapped[int] = mapped_column(Integer)
    motivo: Mapped[str | None] = mapped_column(Text)
    id_bloqueo: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bloqueo_interrupcion.id_bloqueo", ondelete="SET NULL", onupdate="CASCADE")
    )
    es_linea_base: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    tarea: Mapped[Tarea] = relationship(back_populates="reprogramaciones")
    bloqueo: Mapped[BloqueoInterrupcion | None] = relationship()


class ComentarioTarea(Base):
    """Comentario en una tarea; puede mencionar (@) a personas del proyecto."""

    __tablename__ = "comentario_tarea"

    id_comentario: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_tarea: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tarea.id_tarea", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    id_autor: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="SET NULL", onupdate="CASCADE")
    )
    autor_nombre: Mapped[str] = mapped_column(String(150))
    texto: Mapped[str] = mapped_column(Text)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    tarea: Mapped[Tarea] = relationship(back_populates="comentarios")
    menciones: Mapped[list[Mencion]] = relationship(back_populates="comentario", **CASCADE_CHILD)


class Mencion(Base):
    """Persona mencionada en un comentario: es su notificación (leída o no)."""

    __tablename__ = "mencion"
    __table_args__ = (UniqueConstraint("id_comentario", "id_usuario", name="uq_mencion_comentario_usuario"),)

    id_mencion: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_comentario: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("comentario_tarea.id_comentario", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    id_usuario: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    leida: Mapped[bool] = mapped_column(default=False, server_default="false")
    fecha_leida: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    comentario: Mapped[ComentarioTarea] = relationship(back_populates="menciones")
    usuario: Mapped[Usuario] = relationship()

# Título de la tarea del bloqueo, cargado junto con el bloqueo (Tarea se define después).
BloqueoInterrupcion.titulo_tarea = column_property(
    select(Tarea.titulo).where(Tarea.id_tarea == BloqueoInterrupcion.id_tarea).correlate_except(Tarea).scalar_subquery()
)
