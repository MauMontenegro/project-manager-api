"""Ciclo de vida de los proyectos.

Cada departamento configura sus etapas (nombre, orden y estatus permitidos) en `plantilla_etapa`; al crear
un proyecto se copian a sus `etapa_proyecto`, así que cambiar la plantilla no afecta a los proyectos en curso.
Las cinco macro-etapas de aquí son la plantilla inicial de cada departamento.

Todas las etapas de un proyecto pesan lo mismo en su avance (100 % / n). El avance lo calcula
avance_service a partir de las tareas de cada etapa.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.models.enums import EstadoProyecto as E
from app.models.enums import NombreEtapa


@dataclass(frozen=True)
class MacroEtapa:
    orden: int
    nombre: NombreEtapa
    estados: tuple[E, ...]
    descripcion: str


MACRO_ETAPAS: tuple[MacroEtapa, ...] = (
    MacroEtapa(1, NombreEtapa.ANALISIS, (E.SIN_INICIAR, E.ACTIVO, E.EN_REVISION, E.CANCELADO),
               'Se define el "Qué": levantamientos, requerimientos, viabilidad.'),
    MacroEtapa(2, NombreEtapa.DISENO, (E.ACTIVO, E.EN_REVISION, E.PAUSADO, E.CANCELADO),
               'Se define el "Cómo": arquitectura, cronogramas, flujos To-Be.'),
    MacroEtapa(3, NombreEtapa.CONSTRUCCION, (E.ACTIVO, E.BLOQUEADO, E.PAUSADO, E.CANCELADO),
               "Se construye: programar, instalar hardware, redactar manuales."),
    MacroEtapa(4, NombreEtapa.PRUEBAS, (E.ACTIVO, E.EN_REVISION, E.BLOQUEADO, E.CANCELADO),
               "Se valida: QA, UAT, pruebas de estrés, simulaciones."),
    MacroEtapa(5, NombreEtapa.DESPLIEGUE, (E.ACTIVO, E.COMPLETADO),
               "Se lanza y finaliza: Go-Live, encendido, capacitación, cierre."),
)

# Estatus definitivos: el proyecto ya no admite cambios de ciclo ni nuevas asignaciones.
ESTADOS_FINALES = frozenset({E.COMPLETADO, E.CANCELADO})

# Lo que cada departamento puede elegir por etapa. `Activo` siempre se permite (al avanzar de etapa el
# proyecto entra `Activo`), `Sin Iniciar` solo en la primera y `Completado` solo en la última.
ESTADOS_OPCIONALES = (E.EN_REVISION, E.PAUSADO, E.BLOQUEADO, E.CANCELADO)
MAX_ETAPAS = 12


def normalizar_estados(estados: Iterable[E], orden: int, total: int) -> list[str]:
    """Estatus permitidos de la etapa `orden` (1..total) aplicando las reglas fijas, en el orden del enum."""
    elegidos = {e for e in estados if e in ESTADOS_OPCIONALES} | {E.ACTIVO}
    if orden == 1:
        elegidos.add(E.SIN_INICIAR)
    if orden == total:
        elegidos.add(E.COMPLETADO)
    return [e.value for e in E if e in elegidos]


def peso_etapa(total: int) -> Decimal:
    """Porción del avance que vale cada etapa de un proyecto con `total` etapas."""
    return Decimal(100) / Decimal(total) if total else Decimal(0)
