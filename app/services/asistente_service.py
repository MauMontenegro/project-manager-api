"""Señales para el asistente de IA: lo que pide atención en los proyectos que la persona puede ver.

Se calculan con reglas explícitas (vencimientos, bloqueos, semáforo, carga, desfase) para que el modelo no invente
datos: solo las explica, las prioriza y propone qué hacer, citando el proyecto o la tarea.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Actor
from app.models.ciclo_vida import ESTADOS_FINALES
from app.models.enums import EstadoTarea, RolSistema, Semaforo, TipoRecurso
from app.models.operacion import Tarea
from app.models.organizacion import Usuario
from app.models.proyecto import Proyecto
from app.schemas.asistente import Senal, SenalesAsistente
from app.services import bloqueo_service, calendario, capacidad_service, usuario_service, visibilidad

DIAS_BLOQUEO_ALTO = 3   # bloqueo abierto por más de 3 días hábiles: severidad alta
DESFASE_ALTO = 5        # 5+ días hábiles de atraso contra el plan original
MAX_POR_TIPO = 15


def _alcance(actor: Actor) -> str:
    if actor.es_admin:
        return "Todos los proyectos y personas"
    if actor.rol in (RolSistema.GERENTE, RolSistema.LIDER) and actor.departamento:
        return f"Proyectos y personas de {actor.departamento.value}, y los proyectos en que participa"
    return "Los proyectos en que participa y su propia carga"


async def senales(db: AsyncSession, actor: Actor) -> SenalesAsistente:
    hoy = date.today()
    visibles = visibilidad.condicion(actor)
    abiertos = [e.value for e in ESTADOS_FINALES]
    lista: list[Senal] = []

    # Proyectos en riesgo (semáforo calculado por avance vs. fechas).
    stmt = select(Proyecto).where(
        Proyecto.semaforo.in_([Semaforo.ROJO.value, Semaforo.AMARILLO.value]), Proyecto.estado_proyecto.not_in(abiertos),
        Proyecto.es_conjunto.is_(False),
    )
    if visibles is not None:
        stmt = stmt.where(visibles)
    for p in (await db.scalars(stmt.limit(MAX_POR_TIPO))).all():
        lista.append(Senal(
            tipo="proyecto_en_riesgo", severidad="alta" if p.semaforo == Semaforo.ROJO.value else "media",
            titulo=f"«{p.nombre_proyecto}» en {p.semaforo.lower()}",
            detalle=f"Avance {p.porcentaje_avance:.0f} %, etapa {p.etapa_actual or '—'}. {p.semaforo_motivo or ''}".strip(),
            id_proyecto=p.id_proyecto, enlace=f"/proyectos/{p.id_proyecto}",
        ))

    # Tareas vencidas y tareas que esperan a dependencias vencidas.
    stmt = (
        select(Tarea, Proyecto.nombre_proyecto)
        .join(Proyecto, Proyecto.id_proyecto == Tarea.id_proyecto)
        .where(Tarea.estado != EstadoTarea.FINALIZADO.value, Tarea.fecha_fin < hoy, Proyecto.estado_proyecto.not_in(abiertos))
        .order_by(Tarea.fecha_fin)
    )
    if visibles is not None:
        stmt = stmt.where(visibles)
    for t, nombre_proyecto in (await db.execute(stmt.limit(MAX_POR_TIPO))).all():
        dias = (hoy - t.fecha_fin).days
        responsable = await db.get(Usuario, t.id_usuario)
        lista.append(Senal(
            tipo="tarea_vencida", severidad="alta" if dias > 3 else "media",
            titulo=f"«{t.titulo}» venció hace {dias} día(s)",
            detalle=f"{nombre_proyecto} · responsable {responsable.nombre if responsable else '—'} · estado {t.estado}",
            id_proyecto=t.id_proyecto, id_tarea=t.id_tarea, id_usuario=t.id_usuario,
            enlace=f"/proyectos/{t.id_proyecto}?tarea={t.id_tarea}",
        ))

    # Bloqueos reportados abiertos (las esperas por dependencias se ven como su propia señal).
    for b in await bloqueo_service.listar_bloqueos(db, actor, abierto=True, limit=200):
        if b.automatico:
            if b.id_tarea is not None:
                lista.append(Senal(
                    tipo="espera_dependencia", severidad="media",
                    titulo=f"«{b.titulo_tarea}» espera a otras tareas desde hace {b.dias_impacto.normalize():f} día(s) hábiles",
                    detalle=f"{b.nombre_proyecto} · {b.descripcion or 'dependencias sin terminar'}",
                    id_proyecto=b.id_proyecto, id_tarea=b.id_tarea, enlace=f"/proyectos/{b.id_proyecto}?tarea={b.id_tarea}",
                ))
            continue
        alto = b.dias_impacto > DIAS_BLOQUEO_ALTO or b.compromiso_vencido
        que = f"«{b.titulo_tarea}»" if b.titulo_tarea else f"la etapa {b.nombre_etapa}"
        lista.append(Senal(
            tipo="bloqueo_abierto", severidad="alta" if alto else "media",
            titulo=f"{que} bloqueada {b.dias_impacto.normalize():f} día(s) hábiles: {b.causa_raiz}",
            detalle=(
                f"{b.nombre_proyecto} · origen {b.responsable_origen}"
                + (f" · resuelve {b.responsable_resolucion}" if b.responsable_resolucion else "")
                + (f" · compromiso {b.fecha_compromiso:%d/%m/%Y}{' (vencido)' if b.compromiso_vencido else ''}" if b.fecha_compromiso else "")
                + (f" · {b.descripcion}" if b.descripcion else "")
            ),
            id_proyecto=b.id_proyecto, id_tarea=b.id_tarea,
            enlace=f"/proyectos/{b.id_proyecto}?tab=bloqueos" if b.id_tarea is None else f"/proyectos/{b.id_proyecto}?tarea={b.id_tarea}",
        ))

    # Desfase grande contra el plan original.
    resumen = await bloqueo_service.resumen(db, actor)
    for t in resumen.tareas_con_desfase:
        if t.desfase_dias >= DESFASE_ALTO:
            lista.append(Senal(
                tipo="desfase", severidad="alta" if t.desfase_dias >= 2 * DESFASE_ALTO else "media",
                titulo=f"«{t.titulo}» va {t.desfase_dias} días hábiles atrás de su plan original",
                detalle=f"{t.nombre_proyecto} · {t.nombre_usuario} · plan {t.fecha_fin_base:%d/%m} → {t.fecha_fin:%d/%m}",
                id_proyecto=t.id_proyecto, id_tarea=t.id_tarea, enlace=f"/proyectos/{t.id_proyecto}?tarea={t.id_tarea}",
            ))

    # Sobrecarga esta semana: quien gestiona ve a su gente; los demás, solo su propia carga.
    if actor.es_admin:
        personas = await usuario_service.listar_usuarios(db, activo=True, limit=200)
    elif actor.rol in (RolSistema.GERENTE, RolSistema.LIDER) and actor.departamento:
        personas = await usuario_service.listar_usuarios(db, departamento=actor.departamento, activo=True, limit=200)
    elif actor.id_usuario is not None:
        personas = [await usuario_service.obtener_usuario(db, actor.id_usuario)]
    else:
        personas = []
    personas = [u for u in personas if u.tipo_recurso != TipoRecurso.ACTIVO.value]
    nombres = {u.id_usuario: u.nombre for u in personas}
    for c in await capacidad_service.calcular(db, personas, hoy, 1):
        s = c.semanas[0]
        if s.utilizacion is not None and s.utilizacion > 100:
            lista.append(Senal(
                tipo="sobrecarga", severidad="alta" if s.utilizacion > 120 else "media",
                titulo=f"{nombres[c.id_usuario]} al {s.utilizacion:.0f} % esta semana",
                detalle=f"{s.horas_asignadas:.1f} h asignadas de {s.horas_disponibles:.1f} h disponibles para proyectos",
                id_usuario=c.id_usuario, enlace=f"/equipo/{c.id_usuario}",
            ))

    lista.sort(key=lambda x: (x.severidad != "alta", x.tipo))
    return SenalesAsistente(generado=calendario.ahora(), alcance=_alcance(actor), senales=lista)
