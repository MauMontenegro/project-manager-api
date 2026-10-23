"""Proyectos conjuntos: el padre no tiene etapas; su avance y su ciclo se consolidan de sus subproyectos.
Puede tener tareas propias (de coordinación, sin etapa) que no cuentan en el avance.

- Avance: promedio ponderado por las horas presupuestadas de cada subproyecto (promedio simple si
  alguno no tiene presupuesto). Los cancelados no cuentan.
- Fechas: el inicio más temprano y los fines más tardíos. Presupuesto: la suma (nulo si alguno no tiene).
- Semáforo: el peor de los subproyectos no cancelados, con su motivo.
- Estatus: `Completado` si todos cerraron y alguno se completó; `Cancelado` si todos se cancelaron;
  `Sin Iniciar` si ninguno ha iniciado; `Bloqueado` si alguno lo está; si no, `Activo`.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ciclo_vida import ESTADOS_FINALES
from app.models.enums import EstadoProyecto, Semaforo
from app.models.proyecto import Proyecto

GRAVEDAD = {Semaforo.VERDE.value: 0, Semaforo.AMARILLO.value: 1, Semaforo.ROJO.value: 2}


def _estado(estados: set[EstadoProyecto]) -> EstadoProyecto:
    if estados <= ESTADOS_FINALES:
        return EstadoProyecto.COMPLETADO if EstadoProyecto.COMPLETADO in estados else EstadoProyecto.CANCELADO
    if estados <= {EstadoProyecto.SIN_INICIAR, EstadoProyecto.CANCELADO}:
        return EstadoProyecto.SIN_INICIAR
    if EstadoProyecto.BLOQUEADO in estados:
        return EstadoProyecto.BLOQUEADO
    return EstadoProyecto.ACTIVO


def _avance(hijos: list[Proyecto]) -> Decimal:
    if not hijos:
        return Decimal("0.00")
    if all(h.horas_presupuestadas for h in hijos):
        total = sum(h.horas_presupuestadas for h in hijos)
        avance = sum(h.porcentaje_avance * h.horas_presupuestadas for h in hijos) / total
    else:
        avance = sum(h.porcentaje_avance for h in hijos) / len(hijos)
    return Decimal(avance).quantize(Decimal("0.01"))


def aplicar(padre: Proyecto, hijos: list[Proyecto]) -> None:
    if not hijos:
        return
    vigentes = [h for h in hijos if h.estado_proyecto != EstadoProyecto.CANCELADO.value]
    estado = _estado({EstadoProyecto(h.estado_proyecto) for h in hijos})

    padre.estado_proyecto = estado.value
    padre.porcentaje_avance = Decimal("100.00") if estado == EstadoProyecto.COMPLETADO else _avance(vigentes)
    padre.fecha_inicio = min((h.fecha_inicio for h in hijos if h.fecha_inicio), default=None)
    padre.fecha_tentativa = max((h.fecha_tentativa for h in hijos if h.fecha_tentativa), default=None)
    padre.fecha_comprometida = max((h.fecha_comprometida for h in hijos if h.fecha_comprometida), default=None)
    padre.fecha_real_cierre = (
        max((h.fecha_real_cierre for h in hijos if h.fecha_real_cierre), default=None)
        if estado in ESTADOS_FINALES else None
    )
    horas = [h.horas_presupuestadas for h in vigentes]
    padre.horas_presupuestadas = sum(horas) if horas and None not in horas else None
    if vigentes:
        peor = max(vigentes, key=lambda h: GRAVEDAD[h.semaforo])
        padre.semaforo = peor.semaforo
        padre.semaforo_motivo = f"{peor.departamento}: {peor.semaforo_motivo or peor.semaforo}"[:200]
    padre.semaforo_fecha = date.today()


async def consolidar(db: AsyncSession, padre: Proyecto) -> None:
    """Recalcula el conjunto con sus subproyectos tal como están en la sesión (no confirma)."""
    await db.flush()
    hijos = list(await db.scalars(select(Proyecto).where(Proyecto.id_proyecto_padre == padre.id_proyecto)))
    aplicar(padre, hijos)


async def consolidar_padre_de(db: AsyncSession, proyecto: Proyecto) -> None:
    if proyecto.id_proyecto_padre is not None:
        padre = await db.get(Proyecto, proyecto.id_proyecto_padre)
        if padre is not None:
            await consolidar(db, padre)


async def ids_familia(db: AsyncSession, proyecto: Proyecto) -> list[int]:
    """El proyecto y, si es parte de un conjunto, el conjunto con todos sus subproyectos: entre ellos se
    pueden encadenar tareas (dependencias) y colaborar en comentarios."""
    raiz = proyecto.id_proyecto_padre or proyecto.id_proyecto
    return list(await db.scalars(
        select(Proyecto.id_proyecto).where(or_(Proyecto.id_proyecto == raiz, Proyecto.id_proyecto_padre == raiz))
    ))
