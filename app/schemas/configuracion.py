from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConfiguracionLaboralIn(BaseModel):
    horas_entre_semana: Decimal = Field(ge=0, le=24, max_digits=4, decimal_places=2, description="Lunes a viernes")
    horas_sabado: Decimal = Field(ge=0, le=24, max_digits=4, decimal_places=2, description="0 = el sábado no cuenta")
    dias_inactivos: list[date] = Field(default_factory=list, description="Fechas que no cuentan como laborables")

    @field_validator("dias_inactivos")
    @classmethod
    def ordenar(cls, v: list[date]) -> list[date]:
        return sorted(set(v))


class ConfiguracionLaboralRead(ConfiguracionLaboralIn):
    model_config = ConfigDict(from_attributes=True)


class ConfiguracionGuardada(ConfiguracionLaboralRead):
    proyectos_recalculados: int = Field(description="Proyectos abiertos en cálculo automático cuyo presupuesto cambió")
    proyectos_excedidos: int = Field(description="De ellos, cuántos quedaron con más horas en tareas que presupuesto")


class HorasLaborales(BaseModel):
    desde: date
    hasta: date
    horas: Decimal
    dias_laborables: int
