from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Integer, Numeric
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConfiguracionLaboral(Base):
    """Fila única (id = 1) con el calendario laboral que calcula las horas presupuestadas de los proyectos:
    lunes a viernes `horas_entre_semana`, sábado `horas_sabado` (0 = no laboral), domingo nunca."""

    __tablename__ = "configuracion_laboral"
    __table_args__ = (
        CheckConstraint("id = 1", name="fila_unica"),
        CheckConstraint("horas_entre_semana BETWEEN 0 AND 24", name="horas_entre_semana_validas"),
        CheckConstraint("horas_sabado BETWEEN 0 AND 24", name="horas_sabado_validas"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    horas_entre_semana: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal(8), server_default="8")
    horas_sabado: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal(5), server_default="5")
    # Fechas que no cuentan como laborables (festivos, sábados de descanso, etc.).
    dias_inactivos: Mapped[list[date]] = mapped_column(ARRAY(Date), default=list, server_default="{}")
