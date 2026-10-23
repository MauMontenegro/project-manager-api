"""Configuración propia de cada departamento de la DTI: plantilla de etapas y catálogo de etiquetas."""
from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, String, Table, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import DepartamentoProyecto, in_check


class PlantillaEtapa(Base):
    """Etapa del ciclo de vida de un departamento; se copia a cada proyecto nuevo del departamento."""

    __tablename__ = "plantilla_etapa"
    __table_args__ = (
        in_check("departamento", DepartamentoProyecto, "departamento"),
        CheckConstraint("orden > 0", name="orden_positivo"),
        Index("uq_plantilla_etapa_departamento_orden", "departamento", "orden", unique=True),
    )

    id_plantilla: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    departamento: Mapped[str] = mapped_column(String(50))
    orden: Mapped[int] = mapped_column(Integer)
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(Text)
    estados_permitidos: Mapped[list[str]] = mapped_column(ARRAY(String(50)))


class Etiqueta(Base):
    """Tipo de proyecto. Cada departamento administra su catálogo."""

    __tablename__ = "etiqueta"
    __table_args__ = (
        in_check("departamento", DepartamentoProyecto, "departamento"),
        CheckConstraint("color ~ '^#[0-9a-fA-F]{6}$'", name="color_hex"),
    )

    id_etiqueta: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    departamento: Mapped[str] = mapped_column(String(50), index=True)
    nombre: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(7))


# Nombres únicos sin distinguir mayúsculas dentro de cada departamento.
Index("uq_plantilla_etapa_departamento_nombre", PlantillaEtapa.departamento, func.lower(PlantillaEtapa.nombre), unique=True)
Index("uq_etiqueta_departamento_nombre", Etiqueta.departamento, func.lower(Etiqueta.nombre), unique=True)

proyecto_etiqueta = Table(
    "proyecto_etiqueta",
    Base.metadata,
    Column(
        "id_proyecto", BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    ),
    Column(
        "id_etiqueta", BigInteger, ForeignKey("etiqueta.id_etiqueta", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True, index=True,
    ),
)
