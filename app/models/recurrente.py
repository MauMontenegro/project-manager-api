"""Tareas recurrentes: operación del día a día que no es un proyecto.

Una plantilla (diaria, semanal o mensual) pertenece a una persona y genera una `Tarea` por periodo
(recurrente_service.generar), cada una con su propio estatus, horas y comentarios.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Numeric, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.departamento import Etiqueta
from app.models.enums import Frecuencia, in_check

if TYPE_CHECKING:
    from app.models.operacion import Tarea
    from app.models.organizacion import Usuario

tarea_recurrente_etiqueta = Table(
    "tarea_recurrente_etiqueta",
    Base.metadata,
    Column(
        "id_recurrente", BigInteger,
        ForeignKey("tarea_recurrente.id_recurrente", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True,
    ),
    Column(
        "id_etiqueta", BigInteger, ForeignKey("etiqueta.id_etiqueta", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True, index=True,
    ),
)


class TareaRecurrente(Base):
    __tablename__ = "tarea_recurrente"
    __table_args__ = (
        in_check("frecuencia", Frecuencia, "frecuencia"),
        CheckConstraint("horas_por_periodo >= 0", name="horas_no_negativas"),
        CheckConstraint("fecha_fin IS NULL OR fecha_fin >= fecha_inicio", name="fechas_validas"),
    )

    id_recurrente: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    titulo: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text)
    # Responsable: de quién es y a quién se asigna cada tarea generada.
    id_usuario: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    frecuencia: Mapped[str] = mapped_column(String(20))
    horas_por_periodo: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    # Pausada: deja de generar tareas (las ya generadas se conservan).
    activa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Último periodo ya generado; los siguientes se generan al llegar (y se proyectan en la capacidad).
    generada_hasta: Mapped[date | None] = mapped_column(Date)
    id_creador: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="SET NULL", onupdate="CASCADE")
    )
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    usuario: Mapped[Usuario] = relationship(foreign_keys=[id_usuario])
    etiquetas: Mapped[list[Etiqueta]] = relationship(
        secondary=tarea_recurrente_etiqueta, order_by=Etiqueta.nombre, passive_deletes=True
    )
    tareas: Mapped[list[Tarea]] = relationship(back_populates="recurrente", passive_deletes=True)
