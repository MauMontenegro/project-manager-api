from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import Frecuencia
from app.schemas.departamento import EtiquetaRead


class TareaRecurrenteCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    id_usuario: int = Field(description="Responsable; por defecto quien la crea")
    frecuencia: Frecuencia
    horas_por_periodo: Decimal = Field(ge=0, max_digits=8, decimal_places=2, description="Horas de cada tarea generada")
    fecha_inicio: date = Field(description="Desde cuándo se generan tareas (máx. 31 días atrás)")
    fecha_fin: date | None = Field(default=None, description="Hasta cuándo; nulo = sin fin")
    etiquetas: list[int] = Field(default_factory=list, description="Etiquetas del departamento del responsable")

    @model_validator(mode="after")
    def validar_fechas(self) -> "TareaRecurrenteCreate":
        if self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValueError("fecha_fin no puede ser anterior a fecha_inicio")
        return self


class TareaRecurrenteUpdate(BaseModel):
    """Los cambios aplican a las tareas que se generen después; las ya generadas se editan una por una."""

    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    descripcion: str | None = None
    id_usuario: int | None = None
    horas_por_periodo: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    fecha_fin: date | None = None
    activa: bool | None = Field(default=None, description="false la pausa: deja de generar tareas")
    etiquetas: list[int] | None = Field(default=None, description="Reemplaza la lista completa")


class TareaRecurrenteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_recurrente: int
    titulo: str
    descripcion: str | None
    id_usuario: int
    frecuencia: Frecuencia
    horas_por_periodo: Decimal
    fecha_inicio: date
    fecha_fin: date | None
    activa: bool
    generada_hasta: date | None
    fecha_creacion: datetime
    etiquetas: list[EtiquetaRead]
    tareas_abiertas: int = Field(default=0, description="Tareas generadas aún no finalizadas")
