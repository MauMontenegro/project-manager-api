from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import EstadoEtapa, EstadoProyecto, NivelImpacto, NombreEtapa, Semaforo


class ProyectoBase(BaseModel):
    nombre_proyecto: str = Field(min_length=1, max_length=200)
    problema_oportunidad: str = Field(min_length=1)
    objetivo: str = Field(min_length=1)
    alcance: str = Field(min_length=1)
    fuera_de_alcance: str = Field(min_length=1)
    fecha_tentativa: date | None = None
    fecha_comprometida: date | None = None


class EmpresaImpactadaIn(BaseModel):
    id_empresa: int
    nivel_impacto: NivelImpacto
    notas_impacto: str | None = None


class EmpresaImpactadaRead(EmpresaImpactadaIn):
    model_config = ConfigDict(from_attributes=True)


class ProyectoCreate(ProyectoBase):
    lider_id: int
    id_solicitud: int | None = None
    semaforo: Semaforo = Semaforo.VERDE
    empresas_impactadas: list[EmpresaImpactadaIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def validar_empresas_unicas(self) -> "ProyectoCreate":
        ids = [e.id_empresa for e in self.empresas_impactadas]
        if len(ids) != len(set(ids)):
            raise ValueError("empresas_impactadas contiene empresas repetidas")
        return self


class ProyectoUpdate(BaseModel):
    """El estado se modifica solo mediante `PATCH /proyectos/{id}/estado`."""

    nombre_proyecto: str | None = Field(default=None, min_length=1, max_length=200)
    problema_oportunidad: str | None = Field(default=None, min_length=1)
    objetivo: str | None = Field(default=None, min_length=1)
    alcance: str | None = Field(default=None, min_length=1)
    fuera_de_alcance: str | None = Field(default=None, min_length=1)
    fecha_tentativa: date | None = None
    fecha_comprometida: date | None = None
    semaforo: Semaforo | None = None
    lider_id: int | None = None


class ProyectoCambioEstado(BaseModel):
    estado_proyecto: EstadoProyecto
    fecha_real_cierre: date | None = Field(
        default=None, description="Solo aplica al pasar a 'Cierre'; por defecto la fecha actual."
    )


class ProyectoRead(ProyectoBase):
    model_config = ConfigDict(from_attributes=True)

    id_proyecto: int
    id_solicitud: int | None
    lider_id: int
    estado_proyecto: EstadoProyecto
    fecha_real_cierre: date | None
    semaforo: Semaforo


class ProyectoDetalle(ProyectoRead):
    empresas_impactadas: list[EmpresaImpactadaRead] = Field(default_factory=list)


class PortafolioPage(BaseModel):
    items: list[ProyectoRead]
    total: int
    limit: int
    offset: int


class EtapaCreate(BaseModel):
    nombre_etapa: NombreEtapa
    orden_secuencia: int = Field(gt=0)
    horas_estimadas: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    fecha_inicio_est: date | None = None
    fecha_fin_est: date | None = None

    @model_validator(mode="after")
    def validar_fechas(self) -> "EtapaCreate":
        if self.fecha_inicio_est and self.fecha_fin_est and self.fecha_fin_est < self.fecha_inicio_est:
            raise ValueError("fecha_fin_est no puede ser anterior a fecha_inicio_est")
        return self


class EtapaRead(EtapaCreate):
    model_config = ConfigDict(from_attributes=True)

    id_etapa: int
    id_proyecto: int
    horas_efectivas_reales: Decimal
    estado_etapa: EstadoEtapa


class AsignacionCreate(BaseModel):
    id_usuario: int
    id_etapa: int
    perfil_requerido: str = Field(min_length=1, max_length=100)
    horas_asignadas: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    porcentaje_utilizacion: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)


class AsignacionRead(AsignacionCreate):
    model_config = ConfigDict(from_attributes=True)

    id_asignacion: int
    id_proyecto: int
