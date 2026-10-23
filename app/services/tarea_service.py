"""Tareas de proyecto y de tareas recurrentes (operación).

De proyecto: cada cambio que afecta al avance (alta, baja, estado o etapa) lo recalcula y puede hacer
avanzar el proyecto de etapa (ver avance_service). Un proyecto conjunto no tiene etapas: sus tareas
propias van sin etapa y no cuentan en su avance (que se consolida de los subproyectos); su tablero muestra
además las de todos sus subproyectos, que solo se editan en el suyo. Las dependencias pueden cruzar entre
el conjunto y sus subproyectos. Recurrentes: las genera recurrente_service y se gestionan igual (kanban,
horas, comentarios), sin etapa, dependencias ni presupuesto.

Desfases: al crearla, la tarea de proyecto guarda su línea base (fechas originales). Cada cambio de fechas queda
como reprogramación; retrasar la fecha límite exige motivo y puede atribuirse a uno de sus bloqueos (ver
bloqueo_service, que también mide desfase y tiempo bloqueado)."""
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.security import Actor, exigir
from app.models.ciclo_vida import ESTADOS_FINALES
from app.models.departamento import Etiqueta
from app.models.enums import EstadoProyecto, EstadoTarea, Frecuencia
from app.models.operacion import BloqueoInterrupcion, EtapaProyecto, ReprogramacionTarea, Tarea, TareaDependencia
from app.models.organizacion import Usuario
from app.models.proyecto import Proyecto
from app.models.recurrente import TareaRecurrente
from app.models.tablas_uniones import AsignacionRecurso
from app.schemas.tarea import (
    BloqueoActivo, LineaBaseIn, PeriodoBloqueo, ReprogramacionRead, TareaCreate, TareaRead, TareaRelacionada, TareaUpdate,
    _fechas_coherentes,
)
from app.schemas.departamento import EtiquetaRead
from app.services import (
    auditoria_service, avance_service, bloqueo_service, calendario, colaboracion_service, configuracion_service,
    conjunto_service, recurrente_service, visibilidad,
)

MSG_GESTION = "Solo el líder del proyecto, el Gerente de su departamento o el Administrador pueden gestionar sus tareas"


def _gestiona(actor: Actor, proyecto: Proyecto) -> bool:
    return actor.gestiona_proyecto(proyecto)


def _relacionada(t: Tarea) -> TareaRelacionada:
    p = t.proyecto
    return TareaRelacionada(
        id_tarea=t.id_tarea, titulo=t.titulo, estado=t.estado, id_proyecto=t.id_proyecto,
        nombre_proyecto=p.nombre_proyecto if p else None, departamento=p.departamento if p else None,
    )


def _pendientes(t: Tarea) -> list[Tarea]:
    """Dependencias que aún no están Finalizado."""
    return [d for d in t.dependencias if d.estado != EstadoTarea.FINALIZADO.value]


def _leer(t: Tarea, num_comentarios: int, config, ahora: datetime) -> TareaRead:
    p, e, r = t.proyecto, t.etapa, t.recurrente
    abierto = next((b for b in reversed(t.bloqueos) if b.fecha_fin_bloqueo is None), None)
    dias_bloqueada, horas_bloqueada = bloqueo_service.tiempo_bloqueada(config, t.bloqueos, ahora)
    return TareaRead(
        num_comentarios=num_comentarios,
        fecha_inicio_base=t.fecha_inicio_base, fecha_fin_base=t.fecha_fin_base,
        desfase_dias=bloqueo_service.desfase(config, t, ahora.date()) if p else None,
        num_reprogramaciones=sum(not x.es_linea_base for x in t.reprogramaciones),
        dias_bloqueada=dias_bloqueada, horas_bloqueada=horas_bloqueada,
        bloqueo_abierto=BloqueoActivo(
            id_bloqueo=abierto.id_bloqueo, causa_raiz=abierto.causa_raiz, automatico=abierto.automatico,
            descripcion=abierto.descripcion, desde=abierto.fecha_inicio_bloqueo,
            dias=calendario.duracion_habil(config, [bloqueo_service.periodo(abierto, ahora)])[0],
        ) if abierto else None,
        periodos_bloqueo=[
            PeriodoBloqueo(inicio=b.fecha_inicio_bloqueo, fin=b.fecha_fin_bloqueo, automatico=b.automatico, causa_raiz=b.causa_raiz)
            for b in t.bloqueos
        ],
        dependencias=[_relacionada(d) for d in t.dependencias],
        dependientes=[_relacionada(d) for d in t.dependientes],
        bloqueada=bool(_pendientes(t)),
        id_tarea=t.id_tarea, id_proyecto=t.id_proyecto, nombre_proyecto=p.nombre_proyecto if p else None,
        estado_proyecto=p.estado_proyecto if p else None, departamento=p.departamento if p else None,
        id_proyecto_padre=p.id_proyecto_padre if p else None, id_equipo_trabajo=p.id_equipo_trabajo if p else None,
        id_etapa=t.id_etapa, nombre_etapa=e.nombre_etapa if e else None,
        orden_etapa=e.orden_secuencia if e else None,
        id_recurrente=t.id_recurrente, frecuencia=r.frecuencia if r else None, periodo=t.periodo,
        # Las de su tarea recurrente o, en una de proyecto, las del proyecto (para filtrar todas por tipo).
        etiquetas=[EtiquetaRead.model_validate(x) for x in (r.etiquetas if r else p.etiquetas if p else [])],
        id_usuario=t.id_usuario, nombre_usuario=t.usuario.nombre,
        titulo=t.titulo, descripcion=t.descripcion, horas_asignadas=t.horas_asignadas, horas_reales=t.horas_reales,
        fecha_inicio=t.fecha_inicio,
        fecha_fin=t.fecha_fin, estado=t.estado, fecha_creacion=t.fecha_creacion, fecha_finalizacion=t.fecha_finalizacion,
    )


def _consulta():
    return select(Tarea).options(
        selectinload(Tarea.proyecto).selectinload(Proyecto.etiquetas), selectinload(Tarea.etapa), selectinload(Tarea.usuario),
        selectinload(Tarea.recurrente).selectinload(TareaRecurrente.etiquetas),
        # Mismo proyecto que la tarea a veces: se cargan igual (con etiquetas) para que una ruta no deje a la otra a medias.
        selectinload(Tarea.dependencias).selectinload(Tarea.proyecto).selectinload(Proyecto.etiquetas),
        selectinload(Tarea.dependientes).selectinload(Tarea.proyecto).selectinload(Proyecto.etiquetas),
        selectinload(Tarea.bloqueos), selectinload(Tarea.reprogramaciones),
    )


async def _leer_todas(db: AsyncSession, tareas: list[Tarea]) -> list[TareaRead]:
    conteo = await colaboracion_service.conteo_comentarios(db, [t.id_tarea for t in tareas])
    config, ahora = await configuracion_service.obtener(db), calendario.ahora()
    return [_leer(t, conteo.get(t.id_tarea, 0), config, ahora) for t in tareas]


async def _leer_una(db: AsyncSession, id_tarea: int) -> TareaRead:
    return (await _leer_todas(db, [await _obtener(db, id_tarea)]))[0]


async def _sincronizar(db: AsyncSession) -> None:
    """Abre o cierra las esperas automáticas por dependencias antes de leer tareas."""
    if await bloqueo_service.sincronizar_dependencias(db):
        await db.commit()


async def _obtener(db: AsyncSession, id_tarea: int) -> Tarea:
    tarea = await db.scalar(_consulta().where(Tarea.id_tarea == id_tarea).execution_options(populate_existing=True))
    if tarea is None:
        raise NotFoundError(f"Tarea con id {id_tarea} no existe")
    return tarea


async def _proyecto_abierto(db: AsyncSession, id_proyecto: int) -> Proyecto:
    proyecto = await db.get(Proyecto, id_proyecto)
    if proyecto is None:
        raise NotFoundError(f"Proyecto con id {id_proyecto} no existe")
    if EstadoProyecto(proyecto.estado_proyecto) in ESTADOS_FINALES:
        raise BusinessRuleError(f"El proyecto está '{proyecto.estado_proyecto}': sus tareas ya no admiten cambios")
    return proyecto


async def _validar_etapa(db: AsyncSession, proyecto: Proyecto, id_etapa: int | None) -> None:
    """Obligatoria y del proyecto; en un conjunto (que no tiene etapas), ninguna."""
    if proyecto.es_conjunto:
        if id_etapa is not None:
            raise BusinessRuleError("Las tareas propias de un proyecto conjunto no tienen etapa")
        return
    if id_etapa is None:
        raise BusinessRuleError("Indica la etapa de la tarea")
    etapa = await db.get(EtapaProyecto, id_etapa)
    if etapa is None or etapa.id_proyecto != proyecto.id_proyecto:
        raise NotFoundError(f"La etapa {id_etapa} no existe en el proyecto {proyecto.id_proyecto}")


async def _validar_persona(db: AsyncSession, proyecto: Proyecto, id_usuario: int) -> None:
    """La persona debe estar activa y tener una asignación en el proyecto (ser líder no basta). En un conjunto,
    en alguno de sus subproyectos, o ser el líder del conjunto o de un subproyecto."""
    usuario = await db.get(Usuario, id_usuario)
    if usuario is None:
        raise NotFoundError(f"Usuario con id {id_usuario} no existe")
    if not usuario.activo:
        raise BusinessRuleError(f"'{usuario.nombre}' está inactivo")
    if proyecto.es_conjunto:
        familia = await conjunto_service.ids_familia(db, proyecto)
        asignado = await db.scalar(select(
            exists().where(AsignacionRecurso.id_proyecto.in_(familia), AsignacionRecurso.id_usuario == id_usuario)
            | exists().where(Proyecto.id_proyecto.in_(familia), Proyecto.lider_id == id_usuario)
        ))
        if not asignado:
            raise BusinessRuleError(f"'{usuario.nombre}' no participa en el proyecto: asígnalo primero en alguno de sus subproyectos")
        return
    asignado = await db.scalar(
        select(exists().where(AsignacionRecurso.id_proyecto == proyecto.id_proyecto, AsignacionRecurso.id_usuario == id_usuario))
    )
    if not asignado:
        raise BusinessRuleError(f"'{usuario.nombre}' no forma parte del proyecto: asígnalo primero en Asignaciones")


async def _resolver_dependencias(db: AsyncSession, proyecto: Proyecto, ids: list[int], *, id_tarea: int | None = None) -> list[Tarea]:
    """Las dependencias deben ser tareas del mismo proyecto o, si es parte de un conjunto, del conjunto o de
    cualquiera de sus subproyectos; distintas de la tarea y sin formar ciclos."""
    ids = list(dict.fromkeys(ids))
    if id_tarea is not None and id_tarea in ids:
        raise BusinessRuleError("Una tarea no puede depender de sí misma")
    if not ids:
        return []
    familia = await conjunto_service.ids_familia(db, proyecto)
    tareas = {t.id_tarea: t for t in await db.scalars(select(Tarea).where(Tarea.id_tarea.in_(ids)))}
    for i in ids:
        if i not in tareas or tareas[i].id_proyecto not in familia:
            donde = "del mismo proyecto conjunto" if len(familia) > 1 else "del mismo proyecto"
            raise BusinessRuleError(f"La tarea {i} no existe en este proyecto: solo puede depender de tareas {donde}")
    if id_tarea is not None:
        # Ciclo: alguna dependencia ya depende (directa o indirectamente) de esta tarea.
        aristas: dict[int, list[int]] = {}
        filas = await db.execute(
            select(TareaDependencia.id_tarea, TareaDependencia.id_dependencia)
            .join(Tarea, Tarea.id_tarea == TareaDependencia.id_tarea).where(Tarea.id_proyecto.in_(familia))
        )
        for origen, destino in filas:
            aristas.setdefault(origen, []).append(destino)
        for i in ids:
            pila, vistos = [i], set()
            while pila:
                actual = pila.pop()
                if actual == id_tarea:
                    raise BusinessRuleError(
                        f"«{tareas[i].titulo}» ya depende (directa o indirectamente) de esta tarea: se formaría un ciclo"
                    )
                if actual not in vistos:
                    vistos.add(actual)
                    pila.extend(aristas.get(actual, []))
    return [tareas[i] for i in ids]


def _validar_inicio(tarea: Tarea) -> None:
    """Fuera de `Pendiente` solo si todas sus dependencias están `Finalizado`."""
    if tarea.estado == EstadoTarea.PENDIENTE.value:
        return
    pendientes = _pendientes(tarea)
    if pendientes:
        lista = ", ".join(f"«{d.titulo}» ({d.estado})" for d in pendientes)
        raise BusinessRuleError(
            f"«{tarea.titulo}» no puede pasar a «{tarea.estado}»: depende de {lista}, que aún no está(n) terminada(s)"
        )


def _f(d: date) -> str:
    return d.strftime("%d/%m/%Y")


async def horas_en_tareas(db: AsyncSession, id_proyecto: int, *, excluir: int | None = None) -> Decimal:
    stmt = select(func.coalesce(func.sum(Tarea.horas_asignadas), 0)).where(Tarea.id_proyecto == id_proyecto)
    if excluir is not None:
        stmt = stmt.where(Tarea.id_tarea != excluir)
    return Decimal(await db.scalar(stmt))


async def _validar_limites(
    db: AsyncSession, proyecto: Proyecto, *, inicio: date | None, fin: date | None, horas: Decimal,
    excluir: int | None = None,
) -> None:
    """La tarea debe caer dentro de las fechas del proyecto y no exceder su presupuesto de horas (el de un
    conjunto es la suma del de sus subproyectos: sus tareas propias no lo consumen)."""
    for nombre, valor in (("El inicio", inicio), ("La fecha límite", fin)):
        if valor is None:
            continue
        if proyecto.fecha_inicio and valor < proyecto.fecha_inicio:
            raise BusinessRuleError(f"{nombre} de la tarea ({_f(valor)}) es anterior al inicio del proyecto ({_f(proyecto.fecha_inicio)})")
        if proyecto.fecha_fin and valor > proyecto.fecha_fin:
            raise BusinessRuleError(f"{nombre} de la tarea ({_f(valor)}) es posterior al fin del proyecto ({_f(proyecto.fecha_fin)})")

    if proyecto.horas_presupuestadas is not None and not proyecto.es_conjunto:
        usadas = await horas_en_tareas(db, proyecto.id_proyecto, excluir=excluir)
        disponibles = proyecto.horas_presupuestadas - usadas
        if horas > disponibles:
            raise BusinessRuleError(
                f"La tarea ({horas} h) excede el presupuesto del proyecto: quedan {max(disponibles, Decimal(0))} h "
                f"de {proyecto.horas_presupuestadas} h"
            )


async def validar_proyecto_contra_tareas(db: AsyncSession, proyecto: Proyecto) -> None:
    """Al editar fechas o presupuesto del proyecto, sus tareas existentes deben seguir cabiendo."""
    if proyecto.fecha_inicio and proyecto.fecha_fin and proyecto.fecha_fin < proyecto.fecha_inicio:
        raise BusinessRuleError("La fecha de inicio del proyecto no puede ser posterior a su fecha de fin")
    if proyecto.horas_presupuestadas is not None:
        usadas = await horas_en_tareas(db, proyecto.id_proyecto)
        if usadas > proyecto.horas_presupuestadas:
            raise BusinessRuleError(
                f"El presupuesto ({proyecto.horas_presupuestadas} h) es menor que las horas ya asignadas en tareas ({usadas} h)"
            )
    fuera = []
    if proyecto.fecha_inicio:
        fuera.append(or_(Tarea.fecha_inicio < proyecto.fecha_inicio, Tarea.fecha_fin < proyecto.fecha_inicio))
    if proyecto.fecha_fin:
        fuera.append(or_(Tarea.fecha_inicio > proyecto.fecha_fin, Tarea.fecha_fin > proyecto.fecha_fin))
    if fuera:
        n = await db.scalar(select(func.count()).where(Tarea.id_proyecto == proyecto.id_proyecto, or_(*fuera)))
        if n:
            raise BusinessRuleError(f"{n} tarea(s) quedarían fuera de las nuevas fechas del proyecto: ajústalas primero")


# ---------- Trazabilidad (bitácora, entidad = "tarea") ----------
CAMPOS_TRAZADOS = (
    "titulo", "descripcion", "id_etapa", "id_usuario", "horas_asignadas", "horas_reales", "fecha_inicio", "fecha_fin", "estado",
)


def _foto(tarea: Tarea) -> dict:
    return {**{c: getattr(tarea, c) for c in CAMPOS_TRAZADOS}, "dependencias": sorted(d.id_tarea for d in tarea.dependencias)}


async def _nombre_usuario(db: AsyncSession, id_usuario: int | None) -> str:
    u = await db.get(Usuario, id_usuario) if id_usuario else None
    return u.nombre if u else "—"


async def _nombre_etapa(db: AsyncSession, id_etapa: int | None) -> str:
    e = await db.get(EtapaProyecto, id_etapa) if id_etapa else None
    return f"{e.orden_secuencia}. {e.nombre_etapa}" if e else "—"


def _fmt(valor) -> str:
    if valor is None:
        return "sin definir"
    if isinstance(valor, date):
        return _f(valor)
    if isinstance(valor, Decimal):
        return f"{valor.normalize():f} h"
    return str(valor)


async def _titulos(db: AsyncSession, ids: list[int]) -> str:
    tareas = [await db.get(Tarea, i) for i in ids]
    return ", ".join(f"«{t.titulo}»" if t else f"#{i}" for i, t in zip(ids, tareas))


async def _registrar_cambios(db: AsyncSession, actor: Actor, tarea: Tarea, antes: dict, *, nota: str | None = None) -> None:
    """Asienta en la bitácora de la tarea qué cambió, en lenguaje legible (más `nota`, p. ej. el motivo)."""
    diff = auditoria_service.diferencias(antes, _foto(tarea))
    if not diff:
        return
    partes = []
    for campo in diff:
        a, d = antes[campo], _foto(tarea)[campo]
        if campo == "dependencias":
            agregadas, quitadas = [i for i in d if i not in a], [i for i in a if i not in d]
            if agregadas:
                partes.append(f"Ahora depende de {await _titulos(db, agregadas)}")
            if quitadas:
                partes.append(f"Ya no depende de {await _titulos(db, quitadas)}")
        elif campo == "estado":
            partes.append(f"Movida de «{a}» a «{d}»")
        elif campo == "id_usuario":
            partes.append(f"Responsable: {await _nombre_usuario(db, a)} → {await _nombre_usuario(db, d)}")
        elif campo == "id_etapa":
            partes.append(f"Etapa: {await _nombre_etapa(db, a)} → {await _nombre_etapa(db, d)}")
        elif campo == "titulo":
            partes.append(f"Título: «{a}» → «{d}»")
        elif campo == "descripcion":
            partes.append("Descripción actualizada")
        else:
            etiqueta = {
                "horas_asignadas": "Horas", "horas_reales": "Horas reales", "fecha_inicio": "Inicio", "fecha_fin": "Fecha límite",
            }[campo]
            partes.append(f"{etiqueta}: {_fmt(a)} → {_fmt(d)}")
    if nota:
        partes.append(nota)
    auditoria_service.registrar(
        db, actor, entidad="tarea", id_entidad=tarea.id_tarea, id_usuario_afectado=tarea.id_usuario,
        accion="movimiento" if set(diff) == {"estado"} else "edicion", resumen="; ".join(partes), cambios=diff,
    )


def _marcar_finalizacion(tarea: Tarea) -> None:
    if tarea.estado == EstadoTarea.FINALIZADO.value:
        tarea.fecha_finalizacion = tarea.fecha_finalizacion or datetime.now(UTC)
    else:
        tarea.fecha_finalizacion = None


async def listar_tareas_proyecto(
    db: AsyncSession, id_proyecto: int, *, id_etapa: int | None = None, id_usuario: int | None = None,
    estado: EstadoTarea | None = None,
) -> list[TareaRead]:
    """Tareas del proyecto. Las de un conjunto incluyen las de todos sus subproyectos (vista general)."""
    proyecto = await db.get(Proyecto, id_proyecto)
    if proyecto is None:
        raise NotFoundError(f"Proyecto con id {id_proyecto} no existe")
    ids = await conjunto_service.ids_familia(db, proyecto) if proyecto.es_conjunto else [id_proyecto]
    await _sincronizar(db)
    stmt = _consulta().where(Tarea.id_proyecto.in_(ids))
    if id_etapa is not None:
        stmt = stmt.where(Tarea.id_etapa == id_etapa)
    if id_usuario is not None:
        stmt = stmt.where(Tarea.id_usuario == id_usuario)
    if estado is not None:
        stmt = stmt.where(Tarea.estado == estado.value)
    tareas = list(await db.scalars(stmt.order_by(Tarea.fecha_fin.asc().nulls_last(), Tarea.id_tarea)))
    return await _leer_todas(db, tareas)


async def listar_tareas_persona(
    db: AsyncSession, actor: Actor, *, id_usuario: int | None = None, estado: EstadoTarea | None = None,
) -> list[TareaRead]:
    """Tareas de una persona en todos sus proyectos. Sin `id_usuario`, las de quien consulta. Solo Gerentes
    y el Administrador pueden ver las de otra persona."""
    if id_usuario is None:
        id_usuario = actor.id_usuario
    elif id_usuario != actor.id_usuario:
        exigir(actor.gestiona_equipo, "Solo puedes ver tus propias tareas")
    if id_usuario is None:
        return []
    # Las de otra persona: sus recurrentes y las de los proyectos que quien consulta puede ver.
    visibles = None if id_usuario == actor.id_usuario else visibilidad.condicion(actor)
    await recurrente_service.generar(db)
    await _sincronizar(db)
    stmt = _consulta().where(Tarea.id_usuario == id_usuario)
    if visibles is not None:
        stmt = stmt.where(or_(Tarea.id_proyecto.is_(None), Tarea.id_proyecto.in_(select(Proyecto.id_proyecto).where(visibles))))
    if estado is not None:
        stmt = stmt.where(Tarea.estado == estado.value)
    tareas = list(await db.scalars(stmt.order_by(Tarea.fecha_fin.asc().nulls_last(), Tarea.id_tarea)))
    return await _leer_todas(db, tareas)


async def obtener_tarea(db: AsyncSession, actor: Actor, id_tarea: int) -> TareaRead:
    """Una tarea (p. ej. al abrirla desde una notificación). Las de proyecto, quien puede ver su proyecto; las
    recurrentes, quien las ve en su panel (la persona, el Gerente de su departamento o el Administrador)."""
    await _sincronizar(db)
    await visibilidad.exigir_tarea(db, actor, id_tarea)
    tarea = await _obtener(db, id_tarea)
    return (await _leer_todas(db, [tarea]))[0]


async def listar_tareas_recurrentes(
    db: AsyncSession, actor: Actor, *, id_usuario: int | None = None, departamento: str | None = None,
    frecuencia: Frecuencia | None = None, etiquetas: list[int] | None = None, estado: EstadoTarea | None = None,
    desde: date | None = None, hasta: date | None = None, vencidas: bool = False, id_recurrente: int | None = None,
) -> list[TareaRead]:
    """Panel de operación: tareas generadas por las tareas recurrentes que el actor puede ver (las suyas;
    un Gerente, las de su departamento; el Administrador, todas). `desde`/`hasta` filtran por traslape con las
    fechas de la tarea; `vencidas`, las no finalizadas cuyo fin ya pasó."""
    await recurrente_service.generar(db)
    stmt = (
        _consulta().join(TareaRecurrente, TareaRecurrente.id_recurrente == Tarea.id_recurrente)
        .join(Usuario, Usuario.id_usuario == Tarea.id_usuario)
        .where(recurrente_service.filtro_visibles(actor))
    )
    if id_recurrente is not None:
        stmt = stmt.where(Tarea.id_recurrente == id_recurrente)
    if id_usuario is not None:
        stmt = stmt.where(Tarea.id_usuario == id_usuario)
    if departamento is not None:
        stmt = stmt.where(Usuario.departamento == departamento)
    if frecuencia is not None:
        stmt = stmt.where(TareaRecurrente.frecuencia == frecuencia.value)
    if etiquetas:
        stmt = stmt.where(TareaRecurrente.etiquetas.any(Etiqueta.id_etiqueta.in_(etiquetas)))
    if estado is not None:
        stmt = stmt.where(Tarea.estado == estado.value)
    if desde is not None:
        stmt = stmt.where(Tarea.fecha_fin >= desde)
    if hasta is not None:
        stmt = stmt.where(Tarea.fecha_inicio <= hasta)
    if vencidas:
        stmt = stmt.where(Tarea.estado != EstadoTarea.FINALIZADO.value, Tarea.fecha_fin < date.today())
    tareas = list(await db.scalars(stmt.order_by(Tarea.fecha_fin.asc(), Tarea.id_tarea).limit(500)))
    return await _leer_todas(db, tareas)


async def crear_tarea(db: AsyncSession, actor: Actor, id_proyecto: int, data: TareaCreate) -> TareaRead:
    proyecto = await _proyecto_abierto(db, id_proyecto)
    exigir(_gestiona(actor, proyecto), MSG_GESTION)
    await _validar_etapa(db, proyecto, data.id_etapa)
    await _validar_persona(db, proyecto, data.id_usuario)
    await _validar_limites(db, proyecto, inicio=data.fecha_inicio, fin=data.fecha_fin, horas=data.horas_asignadas)
    dependencias = await _resolver_dependencias(db, proyecto, data.dependencias)

    tarea = Tarea(id_proyecto=id_proyecto, **data.model_dump(exclude={"dependencias"}))
    tarea.fecha_inicio_base, tarea.fecha_fin_base = data.fecha_inicio, data.fecha_fin
    tarea.estado = data.estado.value
    tarea.dependencias = dependencias
    _validar_inicio(tarea)
    _marcar_finalizacion(tarea)
    db.add(tarea)
    await db.flush()
    auditoria_service.registrar(
        db, actor, entidad="tarea", id_entidad=tarea.id_tarea, id_usuario_afectado=tarea.id_usuario, accion="alta",
        resumen=f"Creó la tarea · responsable {await _nombre_usuario(db, tarea.id_usuario)} · {_fmt(tarea.horas_asignadas)}"
        f" · {tarea.estado}" + (f" · depende de {await _titulos(db, [d.id_tarea for d in dependencias])}" if dependencias else ""),
    )
    await avance_service.recalcular(db, proyecto, por_tareas=True)
    await bloqueo_service.sincronizar_dependencias(db)
    await db.commit()
    return await _leer_una(db, tarea.id_tarea)


async def actualizar_tarea(db: AsyncSession, actor: Actor, id_tarea: int, data: TareaUpdate) -> TareaRead:
    tarea = await _obtener(db, id_tarea)
    if tarea.id_recurrente is not None:
        return await _actualizar_recurrente(db, actor, tarea, data)
    proyecto = await _proyecto_abierto(db, tarea.id_proyecto)
    cambios = data.model_dump(exclude_unset=True)
    motivo = (cambios.pop("motivo_cambio", None) or "").strip() or None
    id_bloqueo_causa = cambios.pop("id_bloqueo_causa", None)

    if not _gestiona(actor, proyecto):
        exigir(actor.id_usuario == tarea.id_usuario, "Solo la persona asignada o quien gestiona el proyecto puede mover esta tarea")
        exigir(set(cambios) <= {"estado", "horas_reales"}, "Solo puedes cambiar el estado y las horas reales de tus tareas")

    for campo in ("titulo", "id_usuario", "horas_asignadas", "fecha_inicio", "fecha_fin", "estado"):
        if campo in cambios and cambios[campo] is None:
            raise BusinessRuleError(f"{campo} no puede ser nulo")
    if "id_etapa" in cambios:
        await _validar_etapa(db, proyecto, cambios["id_etapa"])
    if "id_usuario" in cambios:
        await _validar_persona(db, proyecto, cambios["id_usuario"])
    nuevas_dependencias = cambios.pop("dependencias", None)
    if nuevas_dependencias is not None:
        nuevas_dependencias = await _resolver_dependencias(db, proyecto, nuevas_dependencias, id_tarea=tarea.id_tarea)

    antes = _foto(tarea)
    for campo, valor in cambios.items():
        setattr(tarea, campo, valor.value if isinstance(valor, EstadoTarea) else valor)
    reprogramacion = await _reprogramar(db, actor, tarea, antes, motivo, id_bloqueo_causa)
    if nuevas_dependencias is not None:
        tarea.dependencias = nuevas_dependencias
    if "estado" in cambios:
        _validar_inicio(tarea)
    if cambios.get("horas_reales") is not None and tarea.estado != EstadoTarea.FINALIZADO.value:
        raise BusinessRuleError("Las horas reales se registran al finalizar la tarea")
    try:
        _fechas_coherentes(tarea.fecha_inicio, tarea.fecha_fin)
    except ValueError as e:
        raise BusinessRuleError(str(e)) from e
    if {"fecha_inicio", "fecha_fin", "horas_asignadas"} & cambios.keys():
        await _validar_limites(
            db, proyecto, inicio=tarea.fecha_inicio, fin=tarea.fecha_fin, horas=tarea.horas_asignadas, excluir=tarea.id_tarea,
        )
    _marcar_finalizacion(tarea)
    await _registrar_cambios(db, actor, tarea, antes, nota=_nota_reprogramacion(reprogramacion))

    if {"estado", "id_etapa"} & cambios.keys():
        await avance_service.recalcular(db, proyecto, por_tareas=True)
    await bloqueo_service.sincronizar_dependencias(db)
    await db.commit()
    return await _leer_una(db, id_tarea)


async def _actualizar_recurrente(db: AsyncSession, actor: Actor, tarea: Tarea, data: TareaUpdate) -> TareaRead:
    """La tarea de un periodo la edita su responsable, el Gerente de su departamento o el Administrador. Sin etapa ni
    dependencias: el resto de las reglas (estado, horas reales, fechas, bitácora) son las mismas."""
    exigir(recurrente_service.gestiona_persona(actor, tarea.usuario), recurrente_service.MSG_GESTION)
    cambios = data.model_dump(exclude_unset=True, exclude={"motivo_cambio", "id_bloqueo_causa"})
    if cambios.get("id_etapa") is not None or cambios.pop("dependencias", None):
        raise BusinessRuleError("Una tarea recurrente no tiene etapa ni dependencias")
    cambios.pop("id_etapa", None)
    for campo in ("titulo", "id_usuario", "horas_asignadas", "fecha_inicio", "fecha_fin", "estado"):
        if campo in cambios and cambios[campo] is None:
            raise BusinessRuleError(f"{campo} no puede ser nulo")
    if "id_usuario" in cambios and cambios["id_usuario"] != tarea.id_usuario:
        nuevo = await db.get(Usuario, cambios["id_usuario"])
        if nuevo is None or not nuevo.activo:
            raise BusinessRuleError(f"Usuario con id {cambios['id_usuario']} no existe o está inactivo")
        exigir(recurrente_service.gestiona_persona(actor, nuevo), recurrente_service.MSG_GESTION)

    antes = _foto(tarea)
    for campo, valor in cambios.items():
        setattr(tarea, campo, valor.value if isinstance(valor, EstadoTarea) else valor)
    if cambios.get("horas_reales") is not None and tarea.estado != EstadoTarea.FINALIZADO.value:
        raise BusinessRuleError("Las horas reales se registran al finalizar la tarea")
    try:
        _fechas_coherentes(tarea.fecha_inicio, tarea.fecha_fin)
    except ValueError as e:
        raise BusinessRuleError(str(e)) from e
    _marcar_finalizacion(tarea)
    await _registrar_cambios(db, actor, tarea, antes)
    await db.commit()
    return await _leer_una(db, tarea.id_tarea)


async def eliminar_tarea(db: AsyncSession, actor: Actor, id_tarea: int) -> None:
    tarea = await _obtener(db, id_tarea)
    if tarea.id_recurrente is not None:
        # Quitar la tarea de un periodo (p. ej. un día que no aplica); la plantilla no la vuelve a generar.
        exigir(recurrente_service.gestiona_persona(actor, tarea.usuario), recurrente_service.MSG_GESTION)
        auditoria_service.registrar(
            db, actor, entidad="tarea", id_entidad=tarea.id_tarea, id_usuario_afectado=tarea.id_usuario, accion="baja",
            resumen=f"Eliminó la tarea «{tarea.titulo}» del periodo {_f(tarea.periodo)}",
        )
        await db.delete(tarea)
        await db.commit()
        return
    proyecto = await _proyecto_abierto(db, tarea.id_proyecto)
    exigir(_gestiona(actor, proyecto), MSG_GESTION)
    auditoria_service.registrar(
        db, actor, entidad="tarea", id_entidad=tarea.id_tarea, id_usuario_afectado=tarea.id_usuario, accion="baja",
        resumen=f"Eliminó la tarea «{tarea.titulo}»",
    )
    await bloqueo_service.quitar_de_tarea(db, tarea)
    await db.delete(tarea)
    await avance_service.recalcular(db, proyecto, por_tareas=True)
    await bloqueo_service.sincronizar_dependencias(db)
    await db.commit()


# ---------- Línea base y reprogramaciones ----------
async def _reprogramar(
    db: AsyncSession, actor: Actor, tarea: Tarea, antes: dict, motivo: str | None, id_bloqueo: int | None,
) -> ReprogramacionTarea | None:
    """Si cambiaron las fechas, registra la reprogramación. Retrasar la fecha límite exige motivo; el bloqueo que lo
    causó (opcional) debe ser de la tarea."""
    if (antes["fecha_inicio"], antes["fecha_fin"]) == (tarea.fecha_inicio, tarea.fecha_fin):
        if id_bloqueo is not None:
            raise BusinessRuleError("El bloqueo causante solo se indica al cambiar las fechas")
        return None
    if tarea.fecha_fin > antes["fecha_fin"] and not motivo:
        raise BusinessRuleError("Indica el motivo del retraso de la fecha límite (motivo_cambio)")
    if id_bloqueo is not None:
        bloqueo = await db.get(BloqueoInterrupcion, id_bloqueo)
        if bloqueo is None or bloqueo.id_tarea != tarea.id_tarea:
            raise BusinessRuleError("El bloqueo causante debe ser uno de los bloqueos de esta tarea")
    config = await configuracion_service.obtener(db)
    rep = ReprogramacionTarea(
        id_tarea=tarea.id_tarea, id_actor=actor.id_usuario, actor_nombre=actor.nombre,
        inicio_antes=antes["fecha_inicio"], inicio_despues=tarea.fecha_inicio, fin_antes=antes["fecha_fin"], fin_despues=tarea.fecha_fin,
        dias_habiles=calendario.dias_habiles_entre(config, antes["fecha_fin"], tarea.fecha_fin), motivo=motivo, id_bloqueo=id_bloqueo,
    )
    db.add(rep)
    return rep


def _nota_reprogramacion(rep: ReprogramacionTarea | None) -> str | None:
    if rep is None or not (rep.motivo or rep.id_bloqueo):
        return None
    return f"Motivo: {rep.motivo or 'sin detalle'}" + (" (por un bloqueo)" if rep.id_bloqueo else "")


async def nueva_linea_base(db: AsyncSession, actor: Actor, id_tarea: int, data: LineaBaseIn) -> TareaRead:
    """Las fechas vigentes pasan a ser el plan original (p. ej. tras un cambio de alcance acordado). El desfase se
    mide desde aquí; el cambio queda en el historial de reprogramaciones y en la bitácora."""
    tarea = await _obtener(db, id_tarea)
    if tarea.id_proyecto is None:
        raise BusinessRuleError("Las tareas recurrentes no tienen línea base")
    proyecto = await _proyecto_abierto(db, tarea.id_proyecto)
    exigir(_gestiona(actor, proyecto), MSG_GESTION)
    config = await configuracion_service.obtener(db)
    base_fin = tarea.fecha_fin_base or tarea.fecha_fin
    db.add(ReprogramacionTarea(
        id_tarea=tarea.id_tarea, id_actor=actor.id_usuario, actor_nombre=actor.nombre, es_linea_base=True, motivo=data.motivo,
        inicio_antes=tarea.fecha_inicio_base or tarea.fecha_inicio, inicio_despues=tarea.fecha_inicio,
        fin_antes=base_fin, fin_despues=tarea.fecha_fin, dias_habiles=calendario.dias_habiles_entre(config, base_fin, tarea.fecha_fin),
    ))
    auditoria_service.registrar(
        db, actor, entidad="tarea", id_entidad=tarea.id_tarea, id_usuario_afectado=tarea.id_usuario, accion="edicion",
        resumen=f"Nueva línea base: fecha límite original {_f(base_fin)} → {_f(tarea.fecha_fin)} · Motivo: {data.motivo}",
    )
    tarea.fecha_inicio_base, tarea.fecha_fin_base = tarea.fecha_inicio, tarea.fecha_fin
    await db.commit()
    return await _leer_una(db, id_tarea)


async def reprogramaciones(db: AsyncSession, id_tarea: int) -> list[ReprogramacionRead]:
    await _obtener(db, id_tarea)
    filas = await db.execute(
        select(ReprogramacionTarea, BloqueoInterrupcion.causa_raiz)
        .outerjoin(BloqueoInterrupcion, BloqueoInterrupcion.id_bloqueo == ReprogramacionTarea.id_bloqueo)
        .where(ReprogramacionTarea.id_tarea == id_tarea).order_by(ReprogramacionTarea.fecha.desc())
    )
    return [
        ReprogramacionRead(
            id_reprogramacion=r.id_reprogramacion, fecha=r.fecha, actor_nombre=r.actor_nombre, inicio_antes=r.inicio_antes,
            inicio_despues=r.inicio_despues, fin_antes=r.fin_antes, fin_despues=r.fin_despues, dias_habiles=r.dias_habiles,
            motivo=r.motivo, id_bloqueo=r.id_bloqueo, causa_bloqueo=causa, es_linea_base=r.es_linea_base,
        )
        for r, causa in filas
    ]
