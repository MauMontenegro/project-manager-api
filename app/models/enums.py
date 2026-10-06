from enum import StrEnum

from sqlalchemy import CheckConstraint


class PerfilTecnico(StrEnum):
    ANALISIS_FUNCIONAL = "Análisis Funcional"
    BACKEND = "Backend"
    FRONTEND = "Frontend"
    TESTING = "Testing"
    INFRAESTRUCTURA = "Infraestructura"
    LIDER = "Líder"
    CLIENTE = "Cliente"


class EstadoDemanda(StrEnum):
    SOLICITADO = "Solicitado"
    ANALIZADO = "Analizado"
    PRIORIZADO = "Priorizado"
    ESPERANDO_CAPACIDAD = "Esperando Capacidad"
    PLANEADO = "Planeado"
    EN_EJECUCION = "En Ejecución"
    RECHAZADO = "Rechazado"


class EstadoProyecto(StrEnum):
    INICIACION = "Iniciación"
    PLANEACION = "Planeación"
    EJECUCION = "Ejecución"
    CIERRE = "Cierre"
    CANCELADO = "Cancelado"
    PAUSADO = "Pausado"


class Semaforo(StrEnum):
    VERDE = "Verde"
    AMARILLO = "Amarillo"
    ROJO = "Rojo"


class NombreEtapa(StrEnum):
    ANALISIS = "Análisis"
    ARQUITECTURA = "Arquitectura"
    DESARROLLO = "Desarrollo"
    TESTING = "Testing"
    IMPLEMENTACION = "Implementación"


class EstadoEtapa(StrEnum):
    PENDIENTE = "Pendiente"
    EN_CURSO = "En Curso"
    DETENIDO = "Detenido"
    COMPLETADO = "Completado"


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
