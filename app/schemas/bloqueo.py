from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from app.models.enums import CausaRaiz, ResponsableOrigen


class BloqueoBase(BaseModel):
    id_proyecto: int
    id_etapa: int
    causa_raiz: CausaRaiz
    responsable_origen: ResponsableOrigen


class BloqueoCreate(BloqueoBase):
    """`fecha_inicio_bloqueo` por defecto es el instante actual. Si se envía `fecha_fin_bloqueo`,
    `dias_impacto` se calcula automáticamente."""

    fecha_inicio_bloqueo: AwareDatetime | None = None
    fecha_fin_bloqueo: AwareDatetime | None = None

    @model_validator(mode="after")
    def validar_fechas(self) -> "BloqueoCreate":
        if self.fecha_inicio_bloqueo and self.fecha_fin_bloqueo and self.fecha_fin_bloqueo < self.fecha_inicio_bloqueo:
            raise ValueError("fecha_fin_bloqueo no puede ser anterior a fecha_inicio_bloqueo")
        return self


class BloqueoUpdate(BaseModel):
    causa_raiz: CausaRaiz | None = None
    responsable_origen: ResponsableOrigen | None = None
    fecha_inicio_bloqueo: AwareDatetime | None = None
    fecha_fin_bloqueo: AwareDatetime | None = None


class BloqueoCerrar(BaseModel):
    fecha_fin_bloqueo: AwareDatetime | None = None


class BloqueoRead(BloqueoBase):
    model_config = ConfigDict(from_attributes=True)

    id_bloqueo: int
    fecha_inicio_bloqueo: datetime
    fecha_fin_bloqueo: datetime | None
    dias_impacto: Decimal | None
