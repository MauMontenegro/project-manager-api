from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TokenAsistente(BaseModel):
    """Token de solo lectura para que el asistente consulte la API en nombre de la persona."""

    token: str
    expira: datetime


class ChatIn(BaseModel):
    mensaje: str = Field(min_length=1, max_length=2000)
    id_conversacion: str | None = Field(None, max_length=128, description="Para continuar la conversación")


class Senal(BaseModel):
    """Un hecho que pide atención, calculado con reglas (no por el modelo): el asistente lo explica y prioriza."""

    tipo: Literal["tarea_vencida", "bloqueo_abierto", "proyecto_en_riesgo", "sobrecarga", "desfase", "espera_dependencia"]
    severidad: Literal["alta", "media"]
    titulo: str
    detalle: str
    id_proyecto: int | None = None
    id_tarea: int | None = None
    id_usuario: int | None = None
    enlace: str | None = Field(None, description="Ruta de la app para abrirlo")


class SenalesAsistente(BaseModel):
    generado: datetime
    alcance: str = Field(description="Qué abarca, según el rol de quien consulta")
    senales: list[Senal]
