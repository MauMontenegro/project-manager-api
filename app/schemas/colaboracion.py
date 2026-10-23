from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Involucrado(BaseModel):
    id_usuario: int
    nombre: str
    es_lider: bool


class ComentarioCreate(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)
    menciones: list[int] = Field(default_factory=list, description="Personas del proyecto mencionadas con @")


class PersonaMencionada(BaseModel):
    id_usuario: int
    nombre: str


class EventoTarea(BaseModel):
    """Una entrada de la línea de tiempo de la tarea: un cambio (bitácora) o un comentario."""

    tipo: Literal["cambio", "comentario"]
    fecha: datetime
    id_actor: int | None
    actor_nombre: str
    # cambio
    accion: str | None = None
    resumen: str | None = None
    cambios: dict[str, Any] | None = None
    # comentario
    id_comentario: int | None = None
    texto: str | None = None
    menciones: list[PersonaMencionada] = Field(default_factory=list)


class Notificacion(BaseModel):
    id_mencion: int
    leida: bool
    fecha: datetime
    autor_nombre: str
    texto: str
    id_tarea: int
    titulo_tarea: str
    # Nulos en una tarea recurrente (operación): entonces viene `id_recurrente`.
    id_proyecto: int | None
    nombre_proyecto: str | None
    id_recurrente: int | None = None


class Notificaciones(BaseModel):
    no_leidas: int
    items: list[Notificacion]
