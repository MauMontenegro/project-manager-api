from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import EstadoProyecto, EstadoTarea, Frecuencia
from app.schemas.departamento import EtiquetaRead


def _fechas_coherentes(inicio: date | None, fin: date | None) -> None:
    if inicio and fin and fin < inicio:
        raise ValueError("fecha_fin no puede ser anterior a fecha_inicio")


class TareaCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    id_etapa: int | None = Field(default=None, description="Obligatoria, salvo en un proyecto conjunto (no tiene etapas)")
    id_usuario: int = Field(
        description="Persona con una asignación en el proyecto (en un conjunto, en alguno de sus subproyectos), responsable de la tarea"
    )
    horas_asignadas: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    fecha_inicio: date = Field(description="Obligatoria: con las fechas se reparte la carga semanal de la persona")
    fecha_fin: date
    estado: EstadoTarea = EstadoTarea.PENDIENTE
    dependencias: list[int] = Field(
        default_factory=list,
        description="Tareas que deben estar Finalizado antes de empezar esta: del mismo proyecto o, en un conjunto, de él o de cualquiera de sus subproyectos",
    )

    @model_validator(mode="after")
    def validar_fechas(self) -> "TareaCreate":
        _fechas_coherentes(self.fecha_inicio, self.fecha_fin)
        return self


class TareaUpdate(BaseModel):
    """La persona asignada solo puede cambiar `estado` y `horas_reales`; el líder, los Gerentes y el Administrador, todo."""

    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    descripcion: str | None = None
    id_etapa: int | None = None
    id_usuario: int | None = None
    horas_asignadas: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    estado: EstadoTarea | None = None
    horas_reales: Decimal | None = Field(
        default=None, ge=0, max_digits=8, decimal_places=2, description="Solo en tareas Finalizado; null la borra"
    )
    dependencias: list[int] | None = Field(default=None, description="Reemplaza la lista completa")
    motivo_cambio: str | None = Field(
        default=None, max_length=1000, description="Obligatorio si la fecha límite se mueve a una fecha posterior"
    )
    id_bloqueo_causa: int | None = Field(default=None, description="Bloqueo de la tarea que causó el cambio de fechas")


class TareaRelacionada(BaseModel):
    id_tarea: int
    titulo: str
    estado: EstadoTarea
    id_proyecto: int | None = None
    nombre_proyecto: str | None = None
    departamento: str | None = Field(default=None, description="Del proyecto de la tarea; null en las propias de un conjunto")


class BloqueoActivo(BaseModel):
    id_bloqueo: int
    causa_raiz: str
    automatico: bool
    descripcion: str | None
    desde: datetime
    dias: Decimal = Field(description="Días hábiles que lleva abierto")


class PeriodoBloqueo(BaseModel):
    inicio: datetime
    fin: datetime | None
    automatico: bool
    causa_raiz: str


class LineaBaseIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=1000)


class ReprogramacionRead(BaseModel):
    id_reprogramacion: int
    fecha: datetime
    actor_nombre: str
    inicio_antes: date
    inicio_despues: date
    fin_antes: date
    fin_despues: date
    dias_habiles: int = Field(description="Cuánto se movió la fecha límite (positivo = se retrasó)")
    motivo: str | None
    id_bloqueo: int | None
    causa_bloqueo: str | None
    es_linea_base: bool


class TareaRead(BaseModel):
    """Tarea de proyecto (campos de proyecto y etapa; sin etapa si es propia de un conjunto) o de un periodo de una tarea recurrente
    (`id_recurrente`, `frecuencia`, `periodo`, `etiquetas`); los campos del otro origen van en null."""

    id_tarea: int
    id_proyecto: int | None
    nombre_proyecto: str | None
    estado_proyecto: EstadoProyecto | None
    departamento: str | None = None
    """Departamento de su proyecto; null en las tareas propias de un conjunto y en las recurrentes."""
    id_proyecto_padre: int | None = None
    """Conjunto al que pertenece su proyecto, si es un subproyecto."""
    id_equipo_trabajo: int | None = None
    """Equipo de trabajo de su proyecto (null en las recurrentes o sin equipo)."""
    id_etapa: int | None
    nombre_etapa: str | None
    orden_etapa: int | None
    id_recurrente: int | None = None
    frecuencia: Frecuencia | None = None
    periodo: date | None = None
    etiquetas: list[EtiquetaRead] = []
    id_usuario: int
    nombre_usuario: str
    titulo: str
    descripcion: str | None
    horas_asignadas: Decimal
    horas_reales: Decimal | None
    fecha_inicio: date
    fecha_fin: date
    estado: EstadoTarea
    fecha_creacion: datetime
    fecha_finalizacion: datetime | None
    num_comentarios: int = 0
    dependencias: list[TareaRelacionada] = []
    """Tareas de las que depende."""
    dependientes: list[TareaRelacionada] = []
    """Tareas que esperan a esta."""
    bloqueada: bool = False
    """Alguna dependencia no está Finalizado: no puede salir de Pendiente."""
    fecha_inicio_base: date | None = None
    fecha_fin_base: date | None = None
    """Línea base (fechas originales); null en las recurrentes."""
    desfase_dias: int | None = None
    """Días hábiles de la fecha límite original a la real (finalización, o fecha vigente / hoy si ya venció). Positivo = atraso."""
    num_reprogramaciones: int = 0
    dias_bloqueada: Decimal = Decimal(0)
    horas_bloqueada: Decimal = Decimal(0)
    """Tiempo hábil total con algún bloqueo (los abiertos, hasta ahora)."""
    bloqueo_abierto: BloqueoActivo | None = None
    periodos_bloqueo: list[PeriodoBloqueo] = []
