"""Carga vs. capacidad semanal del Equipo.

Modelo:
- Capacidad planificable = capacidad semanal × % dedicado a proyectos.
- Horas disponibles de una semana = planificable × (días hábiles sin ausencia / 5).
- La carga sale solo de las tareas abiertas (no `Finalizado`): sus horas se reparten entre los días
  hábiles de su rango de fechas (obligatorias).
  Las asignaciones solo dicen quién participa en qué etapa y con qué rol; no consumen capacidad.
- No consumen capacidad las tareas de etapas completadas o canceladas ni de proyectos completados, cancelados o pausados.
- Operación aparte: las tareas recurrentes abiertas (y los periodos futuros aún no generados, proyectados)
  consumen la capacidad de operación = capacidad semanal × (100 − % dedicado a proyectos).
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.equipo import Ausencia
from app.models.enums import EstadoTarea
from app.models.operacion import EtapaProyecto, Tarea
from app.models.organizacion import Usuario
from app.models.proyecto import Proyecto
from app.schemas.equipo import CapacidadPersona, SemanaCapacidad
from app.services import recurrente_service
from app.services.equipo_service import ESTADOS_ETAPA_SIN_CARGA, ESTADOS_PROYECTO_SIN_CARGA

DIAS_HABILES = 5
UNA_DECIMA = Decimal("0.1")


@dataclass(frozen=True)
class _CargaTarea:
    horas: Decimal
    inicio: date
    fin: date

    def horas_en(self, desde: date, hasta: date) -> Decimal:
        """Parte proporcional de las horas que cae entre `desde` y `hasta`, por días hábiles
        (o naturales si el rango de la tarea no tiene días hábiles)."""
        dias = [self.inicio + timedelta(days=d) for d in range((self.fin - self.inicio).days + 1)]
        habiles = [d for d in dias if d.weekday() < DIAS_HABILES] or dias
        en_rango = sum(1 for d in habiles if desde <= d <= hasta)
        return self.horas * en_rango / len(habiles)


def lunes_de(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


async def calcular(db: AsyncSession, usuarios: list[Usuario], desde: date, semanas: int) -> list[CapacidadPersona]:
    inicio = lunes_de(desde)
    fin = inicio + timedelta(weeks=semanas, days=-1)
    ids = [u.id_usuario for u in usuarios]
    if not ids:
        return []

    tareas: dict[int, list[_CargaTarea]] = defaultdict(list)
    filas = await db.execute(
        select(Tarea.id_usuario, Tarea.horas_asignadas, Tarea.fecha_inicio, Tarea.fecha_fin)
        .outerjoin(EtapaProyecto, EtapaProyecto.id_etapa == Tarea.id_etapa)  # las propias de un conjunto no tienen etapa
        .join(Proyecto, Proyecto.id_proyecto == Tarea.id_proyecto)
        .where(
            Tarea.id_usuario.in_(ids),
            Tarea.estado != EstadoTarea.FINALIZADO.value,
            Tarea.horas_asignadas > 0,
            or_(EtapaProyecto.id_etapa.is_(None), EtapaProyecto.estado_etapa.not_in(ESTADOS_ETAPA_SIN_CARGA)),
            Proyecto.estado_proyecto.not_in(ESTADOS_PROYECTO_SIN_CARGA),
            Tarea.fecha_inicio <= fin,
            Tarea.fecha_fin >= inicio,
        )
    )
    for id_usuario, horas, f_inicio, f_fin in filas:
        tareas[id_usuario].append(_CargaTarea(horas, f_inicio, f_fin))

    operacion: dict[int, list[_CargaTarea]] = defaultdict(list)
    await recurrente_service.generar(db)
    filas = await db.execute(
        select(Tarea.id_usuario, Tarea.horas_asignadas, Tarea.fecha_inicio, Tarea.fecha_fin).where(
            Tarea.id_usuario.in_(ids),
            Tarea.id_recurrente.is_not(None),
            Tarea.estado != EstadoTarea.FINALIZADO.value,
            Tarea.horas_asignadas > 0,
            Tarea.fecha_inicio <= fin,
            Tarea.fecha_fin >= inicio,
        )
    )
    for id_usuario, horas, f_inicio, f_fin in filas:
        operacion[id_usuario].append(_CargaTarea(horas, f_inicio, f_fin))
    for id_usuario, horas, f_inicio, f_fin in await recurrente_service.carga_proyectada(db, ids, inicio, fin):
        operacion[id_usuario].append(_CargaTarea(horas, f_inicio, f_fin))

    ausencias: dict[int, list[Ausencia]] = defaultdict(list)
    for a in await db.scalars(
        select(Ausencia).where(Ausencia.id_usuario.in_(ids), Ausencia.fecha_inicio <= fin, Ausencia.fecha_fin >= inicio)
    ):
        ausencias[a.id_usuario].append(a)

    resultado = []
    for u in usuarios:
        planificable = u.capacidad_horas_semanales * u.porcentaje_proyectos / 100
        de_operacion = u.capacidad_horas_semanales - planificable
        detalle = []
        for i in range(semanas):
            lunes = inicio + timedelta(weeks=i)
            domingo = lunes + timedelta(days=6)
            habiles = [lunes + timedelta(days=d) for d in range(DIAS_HABILES)]
            dias_ausencia = sum(1 for d in habiles if any(a.fecha_inicio <= d <= a.fecha_fin for a in ausencias[u.id_usuario]))
            disponibles = planificable * (DIAS_HABILES - dias_ausencia) / DIAS_HABILES
            asignadas = sum((t.horas_en(lunes, domingo) for t in tareas[u.id_usuario]), Decimal(0))
            op_disponibles = de_operacion * (DIAS_HABILES - dias_ausencia) / DIAS_HABILES
            op_asignadas = sum((t.horas_en(lunes, domingo) for t in operacion[u.id_usuario]), Decimal(0))
            detalle.append(
                SemanaCapacidad(
                    inicio=lunes,
                    horas_disponibles=disponibles.quantize(UNA_DECIMA),
                    horas_asignadas=asignadas.quantize(UNA_DECIMA),
                    utilizacion=(asignadas * 100 / disponibles).quantize(UNA_DECIMA) if disponibles > 0 else None,
                    dias_ausencia=dias_ausencia,
                    horas_operacion_disponibles=op_disponibles.quantize(UNA_DECIMA),
                    horas_operacion_asignadas=op_asignadas.quantize(UNA_DECIMA),
                    utilizacion_operacion=(op_asignadas * 100 / op_disponibles).quantize(UNA_DECIMA) if op_disponibles > 0 else None,
                )
            )
        resultado.append(
            CapacidadPersona(
                id_usuario=u.id_usuario, capacidad_planificable=planificable.quantize(UNA_DECIMA),
                capacidad_operacion=de_operacion.quantize(UNA_DECIMA), semanas=detalle,
            )
        )
    return resultado
