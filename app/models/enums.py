from enum import StrEnum

from sqlalchemy import CheckConstraint


class Departamento(StrEnum):
    """Áreas de la DTI a las que puede pertenecer una persona del Equipo."""

    DIRECCION = "Dirección"
    INFRAESTRUCTURA = "Infraestructura"
    PROCESOS = "Procesos"
    DESARROLLO_SOFTWARE = "Desarrollo de Software"


class DepartamentoProyecto(StrEnum):
    """Departamentos que tienen su propio espacio de proyectos (todos menos Dirección)."""

    INFRAESTRUCTURA = "Infraestructura"
    PROCESOS = "Procesos"
    DESARROLLO_SOFTWARE = "Desarrollo de Software"


class TipoRecurso(StrEnum):
    INTERNO = "Interno"
    EXTERNO = "Externo"
    ACTIVO = "Activo"


class RolSistema(StrEnum):
    """Rol de acceso: Administrador ve y gestiona todo; Gerente, su departamento (personas, proyectos y
    configuración); Líder, crea proyectos en su departamento y gestiona los que lidera; Usuario, consulta y
    trabaja sus propias tareas."""

    ADMINISTRADOR = "Administrador"
    GERENTE = "Gerente"
    LIDER = "Líder"
    USUARIO = "Usuario"


class NivelSkill(StrEnum):
    BASICO = "Básico"
    INTERMEDIO = "Intermedio"
    EXPERTO = "Experto"


class TipoAusencia(StrEnum):
    VACACIONES = "Vacaciones"
    PERMISO = "Permiso"
    INCAPACIDAD = "Incapacidad"
    CAPACITACION = "Capacitación"
    OTRO = "Otro"


class EstadoDemanda(StrEnum):
    SOLICITADO = "Solicitado"
    ANALIZADO = "Analizado"
    PRIORIZADO = "Priorizado"
    ESPERANDO_CAPACIDAD = "Esperando Capacidad"
    PLANEADO = "Planeado"
    EN_EJECUCION = "En Ejecución"
    RECHAZADO = "Rechazado"


class EstadoProyecto(StrEnum):
    """Estatus ("salud") del proyecto en su etapa actual. Las etapas usan los mismos valores."""

    SIN_INICIAR = "Sin Iniciar"
    ACTIVO = "Activo"
    EN_REVISION = "En Revisión"
    PAUSADO = "Pausado"
    BLOQUEADO = "Bloqueado"
    CANCELADO = "Cancelado"
    COMPLETADO = "Completado"


EstadoEtapa = EstadoProyecto


class Semaforo(StrEnum):
    VERDE = "Verde"
    AMARILLO = "Amarillo"
    ROJO = "Rojo"


class NombreEtapa(StrEnum):
    """Macro-etapas por defecto: plantilla inicial de las etapas de cada departamento."""

    ANALISIS = "Análisis y Viabilidad"
    DISENO = "Diseño y Planificación"
    CONSTRUCCION = "Construcción y Ejecución"
    PRUEBAS = "Pruebas y Validación"
    DESPLIEGUE = "Despliegue y Cierre"


class EstadoTarea(StrEnum):
    """Columnas del kanban. Solo `Finalizado` cuenta para el avance."""

    PENDIENTE = "Pendiente"
    EN_PROGRESO = "En progreso"
    EN_REVISION = "En revisión"
    FINALIZADO = "Finalizado"


class Frecuencia(StrEnum):
    """Periodicidad de una tarea recurrente: genera una tarea por día laborable, semana o mes."""

    DIARIA = "Diaria"
    SEMANAL = "Semanal"
    MENSUAL = "Mensual"


class EstadoHito(StrEnum):
    PENDIENTE = "Pendiente"
    ENTREGADO = "Entregado"
    APROBADO = "Aprobado"
    ATRASADO = "Atrasado"


class CausaRaiz(StrEnum):
    CAMBIO_PRIORIDAD = "Cambio de Prioridad"
    DEPENDENCIA_EXTERNA = "Dependencia Externa"
    FALTA_INFORMACION = "Falta de Información"
    RECURSO_REASIGNADO = "Recurso Reasignado"
    INCIDENTE_OPERATIVO = "Incidente Operativo"
    CAMBIO_ALCANCE = "Cambio de Alcance"
    RETRABAJO = "Retrabajo"
    ESPERA_CLIENTE = "Espera del Cliente"
    DECISION_PENDIENTE = "Decisión Pendiente"
    # La registra el sistema: la tarea llegó a su fecha de inicio con dependencias sin terminar.
    DEPENDENCIA_INTERNA = "Dependencia Interna"


class ResponsableOrigen(StrEnum):
    DTI = "DTI"
    CLIENTE = "Cliente"
    TERCERO = "Tercero"


class EstadoCompromiso(StrEnum):
    PENDIENTE = "Pendiente"
    CUMPLIDO = "Cumplido"
    VENCIDO = "Vencido"
    CANCELADO = "Cancelado"


class NivelImpacto(StrEnum):
    ALTO = "Alto"
    MEDIO = "Medio"
    BAJO = "Bajo"


class TipoDependencia(StrEnum):
    BLOQUEANTE = "Bloqueante"
    SECUENCIAL = "Secuencial"
    INFORMATIVA = "Informativa"


def in_check(column: str, enum: type[StrEnum], name: str) -> CheckConstraint:
    """CHECK (columna IN (...)) con los valores del enum."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return CheckConstraint(f"{column} IN ({values})", name=name)
