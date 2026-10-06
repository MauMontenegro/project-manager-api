from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import NivelImpacto, TipoDependencia, in_check

if TYPE_CHECKING:
    from app.models.operacion import EtapaProyecto
    from app.models.organizacion import Empresa, Usuario
    from app.models.proyecto import Proyecto


class AsignacionRecurso(Base):
    __tablename__ = "asignacion_recurso"
    __table_args__ = (
        CheckConstraint("horas_asignadas > 0", name="horas_positivas"),
        CheckConstraint("porcentaje_utilizacion BETWEEN 0 AND 100", name="utilizacion_valida"),
        UniqueConstraint("id_usuario", "id_etapa", name="uq_asignacion_usuario_etapa"),
    )

    id_asignacion: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id_usuario", ondelete="RESTRICT", onupdate="CASCADE"), index=True
    )
    id_etapa: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("etapa_proyecto.id_etapa", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    id_proyecto: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    perfil_requerido: Mapped[str] = mapped_column(String(100))
    horas_asignadas: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    porcentaje_utilizacion: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    usuario: Mapped[Usuario] = relationship(back_populates="asignaciones")
    etapa: Mapped[EtapaProyecto] = relationship(back_populates="asignaciones")
    proyecto: Mapped[Proyecto] = relationship(back_populates="asignaciones")


class ProyectoEmpresaImpactada(Base):
    __tablename__ = "proyecto_empresa_impactada"
    __table_args__ = (in_check("nivel_impacto", NivelImpacto, "nivel_impacto"),)

    id_proyecto: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True
    )
    id_empresa: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("empresa.id_empresa", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
        index=True,
    )
    nivel_impacto: Mapped[str] = mapped_column(String(20))
    notas_impacto: Mapped[str | None] = mapped_column(Text)

    proyecto: Mapped[Proyecto] = relationship(back_populates="empresas_impactadas")
    empresa: Mapped[Empresa] = relationship(back_populates="proyectos_impactados")


class ProyectoDependencia(Base):
    __tablename__ = "proyecto_dependencia"
    __table_args__ = (
        in_check("tipo_dependencia", TipoDependencia, "tipo_dependencia"),
        CheckConstraint("id_proyecto_origen <> id_proyecto_dependiente", name="sin_autodependencia"),
    )

    id_proyecto_origen: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"), primary_key=True
    )
    id_proyecto_dependiente: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("proyecto.id_proyecto", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
        index=True,
    )
    tipo_dependencia: Mapped[str] = mapped_column(String(50))
    descripcion_dependencia: Mapped[str | None] = mapped_column(Text)

    proyecto_origen: Mapped[Proyecto] = relationship(
        back_populates="dependencias_como_origen", foreign_keys=[id_proyecto_origen]
    )
    proyecto_dependiente: Mapped[Proyecto] = relationship(
        back_populates="dependencias_como_dependiente", foreign_keys=[id_proyecto_dependiente]
    )
