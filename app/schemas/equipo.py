from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import Departamento, EstadoEtapa, EstadoProyecto, RolSistema, TipoAusencia
from app.schemas.usuario import NombreSkill


class SesionRead(BaseModel):
    """Usuario autenticado y su alcance, para adaptar la interfaz."""

    id_usuario: int | None
    nombre: str
    correo: str | None
    rol: RolSistema
    departamento: Departamento | None
    auth_habilitada: bool
    # Entró con una contraseña temporal: debe cambiarla antes de usar la app.
    password_temporal: bool = False
    # El asistente de IA está configurado y la sesión es de una persona del Equipo.
    asistente_disponible: bool = False


# ---------- Catálogo de skills ----------
class SkillCatalogoRead(BaseModel):
    id_skill: int
    nombre: str
    personas: int


class SkillRenombrar(BaseModel):
    nombre: NombreSkill


class SkillFusionar(BaseModel):
    id_destino: int


# ---------- Ausencias ----------
class AusenciaCreate(BaseModel):
    tipo: TipoAusencia
    fecha_inicio: date
    fecha_fin: date
    nota: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _rango(self) -> "AusenciaCreate":
        if self.fecha_fin < self.fecha_inicio:
            raise ValueError("fecha_fin no puede ser anterior a fecha_inicio")
        return self


class AusenciaRead(AusenciaCreate):
    model_config = ConfigDict(from_attributes=True)

    id_ausencia: int
    id_usuario: int


# ---------- Capacidad ----------
class SemanaCapacidad(BaseModel):
    inicio: date
    horas_disponibles: Decimal
    horas_asignadas: Decimal
    # null si no hay horas disponibles (p. ej. ausencia toda la semana).
    utilizacion: Decimal | None
    dias_ausencia: int
    # Operación (tareas recurrentes) contra la parte de la capacidad que no es de proyectos.
    horas_operacion_disponibles: Decimal = Decimal(0)
    horas_operacion_asignadas: Decimal = Decimal(0)
    utilizacion_operacion: Decimal | None = None


class CapacidadPersona(BaseModel):
    id_usuario: int
    capacidad_planificable: Decimal
    capacidad_operacion: Decimal = Decimal(0)
    semanas: list[SemanaCapacidad]


# ---------- Asignaciones de una persona ----------
class AsignacionPersonaRead(BaseModel):
    id_asignacion: int
    id_proyecto: int
    nombre_proyecto: str
    estado_proyecto: EstadoProyecto
    id_etapa: int
    nombre_etapa: str
    estado_etapa: EstadoEtapa
    fecha_inicio_est: date | None
    fecha_fin_est: date | None
    perfil_requerido: str
    horas_en_tareas: Decimal
    """Horas estimadas de sus tareas en esa etapa (todas, incluidas las finalizadas)."""
    vigente: bool
    costo_estimado: Decimal | None
    """horas_en_tareas × costo por hora; null si quien consulta no ve costos o no hay tarifa."""


# ---------- Bitácora ----------
class BitacoraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_bitacora: int
    fecha: datetime
    id_actor: int | None
    actor_nombre: str
    entidad: str
    id_entidad: int
    accion: str
    resumen: str
    cambios: dict[str, Any] | None
