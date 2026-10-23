from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.ciclo_vida import MAX_ETAPAS
from app.models.enums import DepartamentoProyecto, EstadoProyecto


class PlantillaEtapaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = None
    estados_permitidos: list[EstadoProyecto] = Field(
        default_factory=list,
        description="Opcionales: En Revisión, Pausado, Bloqueado, Cancelado. Activo siempre se permite, "
        "Sin Iniciar se agrega a la primera etapa y Completado a la última.",
    )

    @field_validator("nombre")
    @classmethod
    def recortar(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        return v


class PlantillaEtapasIn(BaseModel):
    """Lista completa y ordenada: reemplaza las etapas del departamento."""

    etapas: list[PlantillaEtapaIn] = Field(min_length=1, max_length=MAX_ETAPAS)

    @model_validator(mode="after")
    def nombres_unicos(self) -> "PlantillaEtapasIn":
        nombres = [e.nombre.lower() for e in self.etapas]
        if len(nombres) != len(set(nombres)):
            raise ValueError("Hay etapas con el mismo nombre")
        return self


class PlantillaEtapaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    departamento: DepartamentoProyecto
    orden: int
    nombre: str
    descripcion: str | None
    estados_permitidos: list[EstadoProyecto]


class EtiquetaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$", description="Hexadecimal, p. ej. #2563eb")

    @field_validator("nombre")
    @classmethod
    def recortar(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        return v


class EtiquetaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_etiqueta: int
    departamento: DepartamentoProyecto
    nombre: str
    color: str
