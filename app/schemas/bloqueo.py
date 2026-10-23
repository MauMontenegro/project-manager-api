from datetime import date, datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.models.enums import CausaRaiz, ResponsableOrigen


class BloqueoCreate(BaseModel):
    """Bloqueo de una tarea (`id_tarea`: su proyecto y etapa se toman de ella) o, sin tarea, de una etapa
    (`id_proyecto` + `id_etapa`). `fecha_inicio_bloqueo` por defecto es ahora; con `fecha_fin_bloqueo` nace cerrado."""

    id_tarea: int | None = None
    id_proyecto: int | None = None
    id_etapa: int | None = None
    causa_raiz: CausaRaiz
    responsable_origen: ResponsableOrigen
    descripcion: str | None = Field(default=None, max_length=2000)
    responsable_resolucion: str | None = Field(default=None, max_length=150, description="Quién debe destrabarlo")
    fecha_compromiso: date | None = Field(default=None, description="Para cuándo se comprometió la resolución")
    fecha_inicio_bloqueo: AwareDatetime | None = None
    fecha_fin_bloqueo: AwareDatetime | None = None

    @model_validator(mode="after")
    def validar(self) -> "BloqueoCreate":
        if self.id_tarea is None and (self.id_proyecto is None or self.id_etapa is None):
            raise ValueError("Indica la tarea bloqueada o, si no afecta a una tarea, el proyecto y la etapa")
        if self.causa_raiz == CausaRaiz.DEPENDENCIA_INTERNA:
            raise ValueError("Las esperas por dependencias internas las registra el sistema automáticamente")
        if self.fecha_inicio_bloqueo and self.fecha_fin_bloqueo and self.fecha_fin_bloqueo < self.fecha_inicio_bloqueo:
            raise ValueError("fecha_fin_bloqueo no puede ser anterior a fecha_inicio_bloqueo")
        return self


class BloqueoUpdate(BaseModel):
    causa_raiz: CausaRaiz | None = None
    responsable_origen: ResponsableOrigen | None = None
    descripcion: str | None = Field(default=None, max_length=2000)
    responsable_resolucion: str | None = Field(default=None, max_length=150)
    fecha_compromiso: date | None = None
    nota_resolucion: str | None = Field(default=None, max_length=2000)
    fecha_inicio_bloqueo: AwareDatetime | None = None
    fecha_fin_bloqueo: AwareDatetime | None = None


class BloqueoCerrar(BaseModel):
    fecha_fin_bloqueo: AwareDatetime | None = None
    nota_resolucion: str | None = Field(default=None, max_length=2000, description="Cómo se resolvió")


class BloqueoRead(BaseModel):
    id_bloqueo: int
    id_proyecto: int
    nombre_proyecto: str
    id_etapa: int | None
    nombre_etapa: str | None
    id_tarea: int | None
    titulo_tarea: str | None
    id_usuario_tarea: int | None = Field(description="Persona asignada a la tarea (puede reportar y cerrar sus bloqueos)")
    nombre_usuario_tarea: str | None
    causa_raiz: CausaRaiz
    responsable_origen: ResponsableOrigen
    descripcion: str | None
    responsable_resolucion: str | None
    fecha_compromiso: date | None
    compromiso_vencido: bool = Field(description="Abierto y con la fecha compromiso ya pasada")
    nota_resolucion: str | None
    automatico: bool = Field(description="Espera de dependencia: lo abre y cierra el sistema")
    reportado_por_nombre: str | None
    fecha_inicio_bloqueo: datetime
    fecha_fin_bloqueo: datetime | None
    dias_impacto: Decimal = Field(description="Días hábiles bloqueado (si sigue abierto, hasta ahora)")
    horas_impacto: Decimal = Field(description="Horas hábiles bloqueado (si sigue abierto, hasta ahora)")


class ConteoTiempo(BaseModel):
    clave: str
    bloqueos: int
    dias: Decimal


class ProyectoBloqueos(BaseModel):
    id_proyecto: int
    nombre_proyecto: str
    abiertos: int
    dias: Decimal
    desfase_dias: int


class TareaDesfase(BaseModel):
    id_tarea: int
    titulo: str
    id_proyecto: int
    nombre_proyecto: str
    nombre_usuario: str
    estado: str
    fecha_fin_base: date
    fecha_fin: date
    desfase_dias: int
    dias_bloqueada: Decimal


class DesgloseDesfase(BaseModel):
    """De dónde salen los días de desfase de las tareas (suma de los positivos)."""

    total: int
    por_bloqueo: list[ConteoTiempo] = Field(
        description="Días que se movieron fechas límite por un bloqueo, por su origen (`bloqueos`: cuántas reprogramaciones)"
    )
    reprogramado_sin_bloqueo: int = Field(description="Días que se movieron fechas límite sin atribuirlo a un bloqueo")
    ejecucion: int = Field(
        description="Días entre la fecha límite vigente y el término real (o hoy, si ya venció); negativo si terminó antes"
    )


class ResumenBloqueos(BaseModel):
    abiertos: int
    abiertos_automaticos: int
    compromisos_vencidos: int
    bloqueos_periodo: int
    dias_bloqueo: Decimal = Field(description="Suma por tarea de los días hábiles bloqueada (bloqueos unidos)")
    horas_bloqueo: Decimal
    promedio_resolucion_dias: Decimal | None
    tareas_bloqueadas: int
    por_causa: list[ConteoTiempo]
    por_origen: list[ConteoTiempo]
    por_proyecto: list[ProyectoBloqueos]
    desfase: DesgloseDesfase
    tareas_con_desfase: list[TareaDesfase]
