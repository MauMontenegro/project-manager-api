from datetime import datetime

from pydantic import BaseModel, Field


class EquipoTrabajoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=2000)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    miembros: list[int] = Field(default_factory=list, description="Ids de personas; reemplaza la lista completa")


class EquipoTrabajoUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    miembros: list[int] | None = Field(default=None, description="Si se envía, reemplaza la lista completa")


class MiembroRead(BaseModel):
    id_usuario: int
    nombre: str
    departamento: str | None


class EquipoTrabajoRead(BaseModel):
    id_equipo_trabajo: int
    nombre: str
    descripcion: str | None
    color: str
    fecha_creacion: datetime
    miembros: list[MiembroRead]
    proyectos: int = Field(description="Proyectos de primer nivel (un conjunto cuenta una vez)")
    proyectos_abiertos: int
    proyectos_en_riesgo: int = Field(description="Abiertos con semáforo Amarillo o Rojo")
    bloqueos_abiertos: int
