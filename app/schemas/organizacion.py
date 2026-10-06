from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EmpresaCreate(BaseModel):
    nombre_empresa: str = Field(min_length=1, max_length=150)
    division: str = Field(min_length=1, max_length=100)
    grupo: str = Field(min_length=1, max_length=100)


class EmpresaRead(EmpresaCreate):
    model_config = ConfigDict(from_attributes=True)

    id_empresa: int
    activo: bool
    fecha_creacion: datetime


class AreaCreate(BaseModel):
    id_empresa: int
    nombre_area: str = Field(min_length=1, max_length=150)
    codigo_area: str = Field(min_length=1, max_length=50)


class AreaRead(AreaCreate):
    model_config = ConfigDict(from_attributes=True)

    id_area: int
