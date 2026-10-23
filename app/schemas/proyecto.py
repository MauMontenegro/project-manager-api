from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import DepartamentoProyecto, EstadoEtapa, EstadoProyecto, NivelImpacto, Semaforo
from app.schemas.departamento import EtiquetaRead


class ProyectoBase(BaseModel):
    nombre_proyecto: str = Field(min_length=1, max_length=200)
    objetivo: str = Field(min_length=1)
    # Opcionales al crear: suelen definirse ya iniciado el análisis ("" = sin definir).
    problema_oportunidad: str = ""
    alcance: str = ""
    fuera_de_alcance: str = ""
    fecha_inicio: date | None = None
    fecha_tentativa: date | None = None
    fecha_comprometida: date | None = None
    horas_presupuestadas: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2,
        description="Con valor: presupuesto fijado a mano. Nulo u omitido: se calcula con el calendario laboral.",
    )


class EmpresaImpactadaIn(BaseModel):
    id_empresa: int
    id_area: int = Field(description="Área de la empresa impactada; debe pertenecer a esa empresa")
    nivel_impacto: NivelImpacto
    notas_impacto: str | None = None


class EmpresaImpactadaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_empresa: int
    id_area: int | None
    nivel_impacto: NivelImpacto
    notas_impacto: str | None


def _sin_empresas_repetidas(empresas: list[EmpresaImpactadaIn] | None) -> None:
    ids = [e.id_empresa for e in empresas or []]
    if len(ids) != len(set(ids)):
        raise ValueError("empresas_impactadas contiene empresas repetidas")


class SubproyectoIn(BaseModel):
    departamento: DepartamentoProyecto
    lider_id: int


class ProyectoCreate(ProyectoBase):
    """Proyecto de un departamento, o conjunto (`es_conjunto`) con un subproyecto por departamento
    participante. Las fechas y el presupuesto de un conjunto se copian a sus subproyectos."""

    lider_id: int
    departamento: DepartamentoProyecto | None = Field(default=None, description="Obligatorio salvo en un conjunto")
    es_conjunto: bool = False
    subproyectos: list[SubproyectoIn] = Field(default_factory=list, description="Solo en un conjunto; mínimo dos")
    etiquetas: list[int] = Field(default_factory=list, description="Ids de etiquetas de sus departamentos")
    id_equipo_trabajo: int | None = Field(default=None, description="Equipo de trabajo (opcional); los subproyectos lo heredan")
    id_solicitud: int | None = None
    empresas_impactadas: list[EmpresaImpactadaIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def validar(self) -> "ProyectoCreate":
        _sin_empresas_repetidas(self.empresas_impactadas)
        if self.es_conjunto:
            if self.departamento is not None:
                raise ValueError("Un proyecto conjunto no pertenece a un departamento: indica sus subproyectos")
            deptos = [s.departamento for s in self.subproyectos]
            if len(set(deptos)) < 2 or len(deptos) != len(set(deptos)):
                raise ValueError("Un proyecto conjunto necesita al menos dos departamentos distintos")
        else:
            if self.departamento is None:
                raise ValueError("Indica el departamento del proyecto")
            if self.subproyectos:
                raise ValueError("Solo un proyecto conjunto tiene subproyectos")
        return self


class ProyectoUpdate(BaseModel):
    """El ciclo se modifica solo mediante `PATCH /proyectos/{id}/estado`; el semáforo es calculado."""

    nombre_proyecto: str | None = Field(default=None, min_length=1, max_length=200)
    problema_oportunidad: str | None = Field(default=None, description='"" lo deja sin definir')
    objetivo: str | None = Field(default=None, min_length=1)
    alcance: str | None = Field(default=None, description='"" lo deja sin definir')
    fuera_de_alcance: str | None = Field(default=None, description='"" lo deja sin definir')
    fecha_inicio: date | None = None
    fecha_tentativa: date | None = None
    fecha_comprometida: date | None = None
    horas_presupuestadas: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2,
        description="Con valor: lo fija a mano. `null`: vuelve al cálculo automático.",
    )
    lider_id: int | None = None
    departamento: DepartamentoProyecto | None = Field(
        default=None, description="Solo proyectos normales: lo mueve a otro espacio (conserva sus etapas)."
    )
    etiquetas: list[int] | None = Field(default=None, description="Si se envía, reemplaza la lista completa.")
    id_equipo_trabajo: int | None = Field(
        default=None, description="`null` lo deja sin equipo. En un conjunto se aplica a sus subproyectos; un subproyecto no lo cambia."
    )
    empresas_impactadas: list[EmpresaImpactadaIn] | None = Field(
        default=None, description="Si se envía, reemplaza la lista completa (`[]` las quita todas)."
    )

    @model_validator(mode="after")
    def validar_empresas_unicas(self) -> "ProyectoUpdate":
        _sin_empresas_repetidas(self.empresas_impactadas)
        return self


class ProyectoCambioEstado(BaseModel):
    """Mueve el proyecto en su ciclo de vida. El avance no se envía: lo calculan las tareas."""

    etapa_actual: str | None = Field(default=None, description="Nombre de una de las etapas del proyecto")
    estado_proyecto: EstadoProyecto | None = None
    fecha_real_cierre: date | None = Field(
        default=None, description="Solo aplica al pasar a 'Completado'; por defecto la fecha actual."
    )

    @model_validator(mode="after")
    def validar_cambio(self) -> "ProyectoCambioEstado":
        if self.etapa_actual is None and self.estado_proyecto is None:
            raise ValueError("Envía al menos etapa_actual o estado_proyecto")
        return self


class SubproyectoRead(ProyectoBase):
    model_config = ConfigDict(from_attributes=True)

    id_proyecto: int
    id_solicitud: int | None
    lider_id: int
    departamento: DepartamentoProyecto | None
    es_conjunto: bool
    id_proyecto_padre: int | None
    id_equipo_trabajo: int | None
    etapa_actual: str | None
    estado_proyecto: EstadoProyecto
    porcentaje_avance: Decimal
    fecha_real_cierre: date | None
    horas_presupuestadas_manual: bool
    semaforo: Semaforo
    semaforo_motivo: str | None
    etiquetas: list[EtiquetaRead] = Field(default_factory=list)


class ProyectoRead(SubproyectoRead):
    subproyectos: list[SubproyectoRead] = Field(default_factory=list, description="Solo en un conjunto")


class ProyectoRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_proyecto: int
    nombre_proyecto: str
    lider_id: int


class ProyectoDetalle(ProyectoRead):
    padre: ProyectoRef | None = Field(default=None, description="Conjunto al que pertenece (subproyectos)")
    empresas_impactadas: list[EmpresaImpactadaRead] = Field(default_factory=list)
    horas_en_tareas: Decimal = Field(description="Suma de horas asignadas en sus tareas (para el presupuesto)")


class PortafolioPage(BaseModel):
    items: list[ProyectoRead]
    total: int
    limit: int
    offset: int


class EtapaUpdate(BaseModel):
    """Las etapas se copian de la plantilla del departamento al crear el proyecto; solo se planifican horas y fechas.
    Su estatus lo sincroniza el cambio de estado del proyecto."""

    horas_estimadas: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    fecha_inicio_est: date | None = None
    fecha_fin_est: date | None = None


class EtapaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_etapa: int
    id_proyecto: int
    nombre_etapa: str
    orden_secuencia: int
    descripcion: str | None
    estados_permitidos: list[EstadoProyecto]
    horas_estimadas: Decimal
    horas_efectivas_reales: Decimal
    fecha_inicio_est: date | None
    fecha_fin_est: date | None
    estado_etapa: EstadoEtapa


class AsignacionCreate(BaseModel):
    id_usuario: int
    id_etapa: int
    perfil_requerido: str = Field(min_length=1, max_length=100, description="Rol desempeñado en la etapa")


class AsignacionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_asignacion: int
    id_proyecto: int
    id_usuario: int
    id_etapa: int
    perfil_requerido: str
    horas_en_tareas: Decimal = Decimal(0)
    """Horas estimadas de las tareas de la persona en esa etapa (todas, incluidas las finalizadas)."""
