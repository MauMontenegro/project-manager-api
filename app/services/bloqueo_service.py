"""Bloqueos de tareas y desfases.

- Un bloqueo es un periodo en que una tarea (o, sin tarea, una etapa) no pudo avanzar. Lo reportan y cierran
  la persona asignada o quien gestiona el proyecto; no cambia el estatus de la tarea, solo la marca.
- Automáticos: cuando una tarea `Pendiente` llega a su fecha de inicio con dependencias sin terminar, el sistema
  abre un bloqueo «Dependencia Interna» y lo cierra cuando termina la última (ver `sincronizar_dependencias`).
- El tiempo se mide en días y horas hábiles (ver calendario); los bloqueos de una tarea se unen antes de sumar.
- Desfase de una tarea: días hábiles entre su fecha límite original (línea base) y la real (su finalización o,
  si sigue abierta, la fecha límite vigente u hoy si ya venció). Se explica con sus reprogramaciones (cada una
  con motivo y, si aplica, el bloqueo que la causó).
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.security import Actor, exigir
from app.models.ciclo_vida import ESTADOS_FINALES
from app.models.configuracion import ConfiguracionLaboral
from app.models.enums import CausaRaiz, DepartamentoProyecto, EstadoProyecto, EstadoTarea, ResponsableOrigen, RolSistema
from app.models.operacion import BloqueoInterrupcion, EtapaProyecto, Tarea, TareaDependencia
from app.models.organizacion import Usuario
from app.models.proyecto import Proyecto
from app.schemas.bloqueo import (
    BloqueoCerrar, BloqueoCreate, BloqueoRead, BloqueoUpdate, ConteoTiempo, DesgloseDesfase, ProyectoBloqueos,
    ResumenBloqueos, TareaDesfase,
)
from app.services import auditoria_service, calendario, configuracion_service, conjunto_service, visibilidad

MSG_GESTION = "Solo la persona asignada a la tarea o quien gestiona el proyecto puede registrar y cerrar sus bloqueos"
MSG_AUTOMATICO = "Es una espera por dependencias: el sistema lo cierra cuando terminan las tareas de las que depende"
SISTEMA = Actor(id_usuario=None, nombre="Sistema", correo=None, rol=RolSistema.ADMINISTRADOR, departamento=None)
CERO = Decimal("0.00")


# ---------- Tiempo y desfase ----------
def periodo(b: BloqueoInterrupcion, ahora: datetime) -> tuple[datetime, datetime]:
    """Inicio y fin del bloqueo (si sigue abierto, hasta ahora)."""
    return b.fecha_inicio_bloqueo, max(b.fecha_fin_bloqueo or ahora, b.fecha_inicio_bloqueo)


def tiempo_bloqueada(config: ConfiguracionLaboral, bloqueos: list[BloqueoInterrupcion], ahora: datetime) -> tuple[Decimal, Decimal]:
    """(días, horas) hábiles que la tarea estuvo bloqueada, con sus bloqueos unidos."""
    return calendario.duracion_habil(config, [periodo(b, ahora) for b in bloqueos])


def fecha_real(tarea: Tarea, hoy: date) -> date:
    """Cuándo terminó la tarea o, si sigue abierta, su fecha límite vigente (u hoy, si ya venció)."""
    if tarea.estado == EstadoTarea.FINALIZADO.value and tarea.fecha_finalizacion is not None:
        return calendario.fecha_local(tarea.fecha_finalizacion)
    return max(tarea.fecha_fin, hoy)


def desfase(config: ConfiguracionLaboral, tarea: Tarea, hoy: date) -> int:
    """Días hábiles de la fecha límite original a la real (positivo = atraso)."""
    return calendario.dias_habiles_entre(config, tarea.fecha_fin_base or tarea.fecha_fin, fecha_real(tarea, hoy))


# ---------- Lectura ----------
def _consulta():
    usuario_tarea = aliased(Usuario)
    return (
        select(BloqueoInterrupcion, Proyecto.nombre_proyecto, EtapaProyecto.nombre_etapa, Tarea.id_usuario, usuario_tarea.nombre)
        .join(Proyecto, Proyecto.id_proyecto == BloqueoInterrupcion.id_proyecto)
        .outerjoin(EtapaProyecto, EtapaProyecto.id_etapa == BloqueoInterrupcion.id_etapa)
        .outerjoin(Tarea, Tarea.id_tarea == BloqueoInterrupcion.id_tarea)
        .outerjoin(usuario_tarea, usuario_tarea.id_usuario == Tarea.id_usuario)
    )


def _leer(fila, config: ConfiguracionLaboral, ahora: datetime) -> BloqueoRead:
    b, nombre_proyecto, nombre_etapa, id_usuario_tarea, nombre_usuario_tarea = fila
    if b.fecha_fin_bloqueo is not None and b.dias_impacto is not None:
        dias, horas = b.dias_impacto, b.horas_impacto or CERO
    else:
        dias, horas = calendario.duracion_habil(config, [periodo(b, ahora)])
    return BloqueoRead(
        id_bloqueo=b.id_bloqueo, id_proyecto=b.id_proyecto, nombre_proyecto=nombre_proyecto, id_etapa=b.id_etapa,
        nombre_etapa=nombre_etapa, id_tarea=b.id_tarea, titulo_tarea=b.titulo_tarea, id_usuario_tarea=id_usuario_tarea,
        nombre_usuario_tarea=nombre_usuario_tarea, causa_raiz=b.causa_raiz, responsable_origen=b.responsable_origen,
        descripcion=b.descripcion, responsable_resolucion=b.responsable_resolucion, fecha_compromiso=b.fecha_compromiso,
        compromiso_vencido=b.fecha_fin_bloqueo is None and b.fecha_compromiso is not None and b.fecha_compromiso < calendario.hoy(),
        nota_resolucion=b.nota_resolucion, automatico=b.automatico, reportado_por_nombre=b.reportado_por_nombre,
        fecha_inicio_bloqueo=b.fecha_inicio_bloqueo, fecha_fin_bloqueo=b.fecha_fin_bloqueo, dias_impacto=dias, horas_impacto=horas,
    )


async def _bloqueo(db: AsyncSession, id_bloqueo: int) -> BloqueoInterrupcion:
    bloqueo = await db.get(BloqueoInterrupcion, id_bloqueo)
    if bloqueo is None:
        raise NotFoundError(f"Bloqueo con id {id_bloqueo} no existe")
    return bloqueo


async def obtener_bloqueo(db: AsyncSession, id_bloqueo: int, actor: Actor | None = None) -> BloqueoRead:
    """Con `actor`, solo si puede ver su proyecto."""
    fila = (await db.execute(
        _consulta().where(BloqueoInterrupcion.id_bloqueo == id_bloqueo).execution_options(populate_existing=True)
    )).first()
    if fila is None or (actor is not None and not await visibilidad.puede_ver(db, actor, fila[0].id_proyecto)):
        raise NotFoundError(f"Bloqueo con id {id_bloqueo} no existe")
    return _leer(fila, await configuracion_service.obtener(db), calendario.ahora())


async def _ids_proyectos(
    db: AsyncSession, id_proyecto: int | None, departamento: DepartamentoProyecto | None, id_equipo_trabajo: int | None = None,
    actor: Actor | None = None,
) -> list[int] | None:
    """Proyectos en alcance: uno (un conjunto, con sus subproyectos), los de un departamento y/o de un equipo de
    trabajo, o todos (None); con `actor`, solo los que puede ver."""
    ids = await _alcance(db, id_proyecto, departamento, id_equipo_trabajo)
    if actor is None:
        return ids
    if id_proyecto is not None:
        await visibilidad.exigir_proyecto(db, actor, id_proyecto)
    visibles = await visibilidad.ids_visibles(db, actor)
    if visibles is None:
        return ids
    return visibles if ids is None else sorted(set(ids) & set(visibles))


async def _alcance(
    db: AsyncSession, id_proyecto: int | None, departamento: DepartamentoProyecto | None, id_equipo_trabajo: int | None,
) -> list[int] | None:
    if id_proyecto is not None:
        proyecto = await db.get(Proyecto, id_proyecto)
        if proyecto is None:
            raise NotFoundError(f"Proyecto con id {id_proyecto} no existe")
        return await conjunto_service.ids_familia(db, proyecto) if proyecto.es_conjunto else [id_proyecto]
    if departamento is None and id_equipo_trabajo is None:
        return None
    stmt = select(Proyecto.id_proyecto)
    if departamento is not None:
        stmt = stmt.where(Proyecto.departamento == departamento.value)
    if id_equipo_trabajo is not None:
        stmt = stmt.where(Proyecto.id_equipo_trabajo == id_equipo_trabajo)
    return list(await db.scalars(stmt))


async def listar_bloqueos(
    db: AsyncSession, actor: Actor, *, id_proyecto: int | None = None, departamento: DepartamentoProyecto | None = None,
    id_equipo_trabajo: int | None = None, id_etapa: int | None = None, id_tarea: int | None = None, causa_raiz: CausaRaiz | None = None,
    responsable_origen: ResponsableOrigen | None = None, abierto: bool | None = None, automatico: bool | None = None,
    limit: int = 50, offset: int = 0,
) -> list[BloqueoRead]:
    if await sincronizar_dependencias(db):
        await db.commit()
    stmt = _consulta()
    ids = await _ids_proyectos(db, id_proyecto, departamento, id_equipo_trabajo, actor)
    if ids is not None:
        stmt = stmt.where(BloqueoInterrupcion.id_proyecto.in_(ids))
    if id_etapa is not None:
        stmt = stmt.where(BloqueoInterrupcion.id_etapa == id_etapa)
    if id_tarea is not None:
        stmt = stmt.where(BloqueoInterrupcion.id_tarea == id_tarea)
    if causa_raiz is not None:
        stmt = stmt.where(BloqueoInterrupcion.causa_raiz == causa_raiz.value)
    if responsable_origen is not None:
        stmt = stmt.where(BloqueoInterrupcion.responsable_origen == responsable_origen.value)
    if abierto is not None:
        stmt = stmt.where(BloqueoInterrupcion.fecha_fin_bloqueo.is_(None) if abierto else BloqueoInterrupcion.fecha_fin_bloqueo.is_not(None))
    if automatico is not None:
        stmt = stmt.where(BloqueoInterrupcion.automatico.is_(automatico))
    stmt = stmt.order_by(BloqueoInterrupcion.fecha_fin_bloqueo.is_not(None), BloqueoInterrupcion.fecha_inicio_bloqueo.desc())
    filas = (await db.execute(stmt.limit(limit).offset(offset))).all()
    config, ahora = await configuracion_service.obtener(db), calendario.ahora()
    return [_leer(f, config, ahora) for f in filas]


# ---------- Registro manual ----------
def _puede(actor: Actor, proyecto: Proyecto, tarea: Tarea | None) -> bool:
    return actor.gestiona_proyecto(proyecto) or (tarea is not None and actor.id_usuario is not None and actor.id_usuario == tarea.id_usuario)


async def _contexto(db: AsyncSession, b: BloqueoInterrupcion) -> tuple[Proyecto, Tarea | None]:
    return await db.get(Proyecto, b.id_proyecto), await db.get(Tarea, b.id_tarea) if b.id_tarea else None


def _auditar(db: AsyncSession, actor: Actor, b: BloqueoInterrupcion, tarea: Tarea | None, accion: str, resumen: str) -> None:
    """En la bitácora de la tarea (así aparece en su línea de tiempo) o, sin tarea, en la del proyecto."""
    if tarea is not None:
        auditoria_service.registrar(
            db, actor, entidad="tarea", id_entidad=tarea.id_tarea, id_usuario_afectado=tarea.id_usuario, accion=accion, resumen=resumen,
        )
    else:
        auditoria_service.registrar(db, actor, entidad="proyecto", id_entidad=b.id_proyecto, accion=accion, resumen=resumen)


def _medir(config: ConfiguracionLaboral, b: BloqueoInterrupcion) -> None:
    if b.fecha_fin_bloqueo is None:
        b.dias_impacto = b.horas_impacto = None
    else:
        b.dias_impacto, b.horas_impacto = calendario.duracion_habil(config, [(b.fecha_inicio_bloqueo, b.fecha_fin_bloqueo)])


def _texto_tiempo(b: BloqueoInterrupcion) -> str:
    return f"{b.dias_impacto.normalize():f} días hábiles ({b.horas_impacto.normalize():f} h)"


async def registrar_bloqueo(db: AsyncSession, actor: Actor, data: BloqueoCreate) -> BloqueoRead:
    tarea = None
    if data.id_tarea is not None:
        tarea = await db.get(Tarea, data.id_tarea)
        if tarea is None:
            raise NotFoundError(f"Tarea con id {data.id_tarea} no existe")
        if tarea.id_proyecto is None:
            raise BusinessRuleError("Las tareas recurrentes no registran bloqueos")
        if tarea.estado == EstadoTarea.FINALIZADO.value:
            raise BusinessRuleError(f"«{tarea.titulo}» ya está finalizada")
        id_proyecto, id_etapa = tarea.id_proyecto, tarea.id_etapa
    else:
        id_proyecto, id_etapa = data.id_proyecto, data.id_etapa
        etapa = await db.get(EtapaProyecto, id_etapa)
        if etapa is None or etapa.id_proyecto != id_proyecto:
            raise NotFoundError(f"La etapa {id_etapa} no existe en el proyecto {id_proyecto}")
    proyecto = await db.get(Proyecto, id_proyecto)
    if proyecto is None:
        raise NotFoundError(f"Proyecto con id {id_proyecto} no existe")
    exigir(_puede(actor, proyecto, tarea), MSG_GESTION)
    if EstadoProyecto(proyecto.estado_proyecto) in ESTADOS_FINALES:
        raise BusinessRuleError(f"El proyecto está '{proyecto.estado_proyecto}': ya no registra bloqueos")

    ahora = calendario.ahora()
    inicio = data.fecha_inicio_bloqueo or ahora
    if inicio > ahora + timedelta(minutes=5):
        raise BusinessRuleError("Un bloqueo no puede iniciar en el futuro")
    b = BloqueoInterrupcion(
        id_proyecto=id_proyecto, id_etapa=id_etapa, id_tarea=data.id_tarea, causa_raiz=data.causa_raiz.value,
        responsable_origen=data.responsable_origen.value, descripcion=data.descripcion or None,
        responsable_resolucion=data.responsable_resolucion or None, fecha_compromiso=data.fecha_compromiso,
        fecha_inicio_bloqueo=inicio, fecha_fin_bloqueo=data.fecha_fin_bloqueo, automatico=False,
        id_reportado_por=actor.id_usuario, reportado_por_nombre=actor.nombre,
    )
    config = await configuracion_service.obtener(db)
    _medir(config, b)
    db.add(b)
    await db.flush()
    _auditar(
        db, actor, b, tarea, "bloqueo",
        f"Reportó un bloqueo: {b.causa_raiz} (origen {b.responsable_origen})" + (f" · {b.descripcion}" if b.descripcion else "")
        + (f" · resuelto, {_texto_tiempo(b)}" if b.fecha_fin_bloqueo else ""),
    )
    await db.commit()
    return await obtener_bloqueo(db, b.id_bloqueo)


async def cerrar_bloqueo(db: AsyncSession, actor: Actor, id_bloqueo: int, data: BloqueoCerrar) -> BloqueoRead:
    b = await _bloqueo(db, id_bloqueo)
    if b.automatico:
        raise BusinessRuleError(MSG_AUTOMATICO)
    proyecto, tarea = await _contexto(db, b)
    exigir(_puede(actor, proyecto, tarea), MSG_GESTION)
    if b.fecha_fin_bloqueo is not None:
        raise BusinessRuleError("El bloqueo ya está resuelto")
    fin = data.fecha_fin_bloqueo or calendario.ahora()
    if fin < b.fecha_inicio_bloqueo:
        raise BusinessRuleError("La resolución no puede ser anterior al inicio del bloqueo")
    b.fecha_fin_bloqueo = fin
    b.nota_resolucion = data.nota_resolucion or b.nota_resolucion
    _medir(await configuracion_service.obtener(db), b)
    _auditar(
        db, actor, b, tarea, "desbloqueo",
        f"Resolvió el bloqueo «{b.causa_raiz}» tras {_texto_tiempo(b)}" + (f" · {b.nota_resolucion}" if b.nota_resolucion else ""),
    )
    await db.commit()
    return await obtener_bloqueo(db, id_bloqueo)


async def actualizar_bloqueo(db: AsyncSession, actor: Actor, id_bloqueo: int, data: BloqueoUpdate) -> BloqueoRead:
    b = await _bloqueo(db, id_bloqueo)
    if b.automatico:
        raise BusinessRuleError(MSG_AUTOMATICO)
    proyecto, tarea = await _contexto(db, b)
    exigir(_puede(actor, proyecto, tarea), MSG_GESTION)
    cambios = data.model_dump(exclude_unset=True)
    for campo in ("causa_raiz", "responsable_origen", "fecha_inicio_bloqueo"):
        if campo in cambios and cambios[campo] is None:
            raise BusinessRuleError(f"{campo} no puede ser nulo")
    if cambios.get("causa_raiz") == CausaRaiz.DEPENDENCIA_INTERNA:
        raise BusinessRuleError("Las esperas por dependencias internas las registra el sistema automáticamente")
    for campo, valor in cambios.items():
        setattr(b, campo, valor.value if isinstance(valor, (CausaRaiz, ResponsableOrigen)) else valor)
    if b.fecha_fin_bloqueo is not None and b.fecha_fin_bloqueo < b.fecha_inicio_bloqueo:
        raise BusinessRuleError("La resolución no puede ser anterior al inicio del bloqueo")
    _medir(await configuracion_service.obtener(db), b)
    _auditar(db, actor, b, tarea, "edicion", f"Editó el bloqueo «{b.causa_raiz}» ({', '.join(cambios) or 'sin cambios'})")
    await db.commit()
    return await obtener_bloqueo(db, id_bloqueo)


async def eliminar_bloqueo(db: AsyncSession, actor: Actor, id_bloqueo: int) -> None:
    """Para registros equivocados; solo quien gestiona el proyecto. Un bloqueo real se resuelve, no se borra."""
    b = await _bloqueo(db, id_bloqueo)
    if b.automatico:
        raise BusinessRuleError(MSG_AUTOMATICO)
    proyecto, tarea = await _contexto(db, b)
    exigir(actor.gestiona_proyecto(proyecto), "Solo quien gestiona el proyecto puede eliminar bloqueos")
    _auditar(db, actor, b, tarea, "baja", f"Eliminó el bloqueo «{b.causa_raiz}» del {calendario.fecha_local(b.fecha_inicio_bloqueo):%d/%m/%Y}")
    await db.delete(b)
    await db.commit()


async def quitar_de_tarea(db: AsyncSession, tarea: Tarea) -> None:
    """Antes de borrar una tarea: sus esperas automáticas (y, si no tiene etapa, todos sus bloqueos) ya no
    tienen a qué quedar ligados; los manuales de una tarea con etapa se quedan en la etapa."""
    condicion = BloqueoInterrupcion.automatico.is_(True)
    if tarea.id_etapa is None:
        condicion = condicion | BloqueoInterrupcion.id_etapa.is_(None)
    await db.execute(delete(BloqueoInterrupcion).where(BloqueoInterrupcion.id_tarea == tarea.id_tarea, condicion))


# ---------- Esperas por dependencias (automáticas) ----------
def _lista(tareas: list[Tarea]) -> str:
    return ", ".join(f"«{t.titulo}»" for t in tareas)


async def sincronizar_dependencias(db: AsyncSession) -> bool:
    """Abre un bloqueo automático en cada tarea `Pendiente` que ya llegó a su fecha de inicio con dependencias sin
    terminar, y cierra los de las que ya no esperan (al terminar su última dependencia). No confirma; devuelve si
    cambió algo."""
    hoy, ahora = calendario.hoy(), calendario.ahora()
    dep = aliased(Tarea)
    pendiente = exists().where(
        TareaDependencia.id_tarea == Tarea.id_tarea, dep.id_tarea == TareaDependencia.id_dependencia,
        dep.estado != EstadoTarea.FINALIZADO.value,
    )
    esperando = list(await db.scalars(
        select(Tarea).options(selectinload(Tarea.dependencias).selectinload(Tarea.usuario))
        .where(Tarea.id_recurrente.is_(None), Tarea.estado == EstadoTarea.PENDIENTE.value, Tarea.fecha_inicio <= hoy, pendiente)
    ))
    abiertos = {b.id_tarea: b for b in await db.scalars(
        select(BloqueoInterrupcion).where(BloqueoInterrupcion.automatico.is_(True), BloqueoInterrupcion.fecha_fin_bloqueo.is_(None))
    )}
    cambio = False
    for t in esperando:
        faltan = [d for d in t.dependencias if d.estado != EstadoTarea.FINALIZADO.value]
        descripcion = f"Espera a {_lista(faltan)}"
        responsables = ", ".join(dict.fromkeys(d.usuario.nombre for d in faltan))[:150]
        b = abiertos.pop(t.id_tarea, None)
        if b is not None:
            if (b.descripcion, b.responsable_resolucion) != (descripcion, responsables):
                b.descripcion, b.responsable_resolucion, cambio = descripcion, responsables, True
            continue
        # Desde su fecha de inicio (o desde que se creó, si se dio de alta con el inicio ya pasado).
        inicio = max(datetime.combine(t.fecha_inicio, time.min, calendario.zona()), t.fecha_creacion)
        db.add(BloqueoInterrupcion(
            id_proyecto=t.id_proyecto, id_etapa=t.id_etapa, id_tarea=t.id_tarea, causa_raiz=CausaRaiz.DEPENDENCIA_INTERNA.value,
            responsable_origen=ResponsableOrigen.DTI.value, descripcion=descripcion, responsable_resolucion=responsables,
            automatico=True, fecha_inicio_bloqueo=min(inicio, ahora), reportado_por_nombre=SISTEMA.nombre,
        ))
        auditoria_service.registrar(
            db, SISTEMA, entidad="tarea", id_entidad=t.id_tarea, id_usuario_afectado=t.id_usuario, accion="bloqueo",
            resumen=f"Bloqueada automáticamente: llegó su fecha de inicio y espera a {_lista(faltan)}",
        )
        cambio = True

    if abiertos:
        config = await configuracion_service.obtener(db)
        for b in abiertos.values():  # ya no esperan: terminaron sus dependencias, se quitaron o cambió la tarea
            tarea = await db.scalar(select(Tarea).options(selectinload(Tarea.dependencias)).where(Tarea.id_tarea == b.id_tarea)) if b.id_tarea else None
            terminadas = [d.fecha_finalizacion for d in (tarea.dependencias if tarea else []) if d.fecha_finalizacion]
            todas = tarea is not None and len(terminadas) == len(tarea.dependencias) and terminadas
            b.fecha_fin_bloqueo = max(max(terminadas) if todas else ahora, b.fecha_inicio_bloqueo)
            _medir(config, b)
            if tarea is not None:
                auditoria_service.registrar(
                    db, SISTEMA, entidad="tarea", id_entidad=tarea.id_tarea, id_usuario_afectado=tarea.id_usuario, accion="desbloqueo",
                    resumen=("Se liberó: terminaron sus dependencias" if todas else "Ya no espera dependencias")
                    + f" · estuvo bloqueada {_texto_tiempo(b)}",
                )
        cambio = True
    if cambio:
        await db.flush()
    return cambio


# ---------- Resumen (seguimiento) ----------
async def resumen(
    db: AsyncSession, actor: Actor, *, id_proyecto: int | None = None, departamento: DepartamentoProyecto | None = None,
    id_equipo_trabajo: int | None = None, desde: date | None = None, hasta: date | None = None,
) -> ResumenBloqueos:
    """Bloqueos y desfases de un proyecto (un conjunto, con sus subproyectos), de un departamento o de todo el
    portafolio. `desde`/`hasta` acotan el tiempo de bloqueo a ese rango (por defecto, todo)."""
    if await sincronizar_dependencias(db):
        await db.commit()
    config, ahora, hoy = await configuracion_service.obtener(db), calendario.ahora(), calendario.hoy()
    ids = await _ids_proyectos(db, id_proyecto, departamento, id_equipo_trabajo, actor)
    tz = calendario.zona()
    ventana_ini = datetime.combine(desde, time.min, tz) if desde else None
    ventana_fin = min(datetime.combine(hasta + timedelta(days=1), time.min, tz), ahora) if hasta else ahora

    stmt = select(BloqueoInterrupcion, Proyecto.nombre_proyecto).join(Proyecto, Proyecto.id_proyecto == BloqueoInterrupcion.id_proyecto)
    if ids is not None:
        stmt = stmt.where(BloqueoInterrupcion.id_proyecto.in_(ids))
    filas = (await db.execute(stmt)).all()
    nombres = {b.id_proyecto: n for b, n in filas}

    def recorte(b: BloqueoInterrupcion) -> tuple[datetime, datetime] | None:
        inicio, fin = periodo(b, ahora)
        inicio, fin = max(inicio, ventana_ini) if ventana_ini else inicio, min(fin, ventana_fin)
        return (inicio, fin) if fin > inicio else None

    en_rango = [(b, r) for b, _ in filas if (r := recorte(b)) is not None]
    abiertos = [b for b, _ in filas if b.fecha_fin_bloqueo is None]

    # Tiempo: por tarea (o por bloqueo de etapa), con sus periodos unidos.
    por_tarea: dict[tuple, list[tuple[datetime, datetime]]] = defaultdict(list)
    proyecto_de: dict[tuple, int] = {}
    for b, r in en_rango:
        clave = ("t", b.id_tarea) if b.id_tarea else ("b", b.id_bloqueo)
        por_tarea[clave].append(r)
        proyecto_de[clave] = b.id_proyecto
    dias_total = horas_total = CERO
    dias_proyecto: dict[int, Decimal] = defaultdict(Decimal)
    dias_tarea: dict[int, Decimal] = {}
    for clave, periodos in por_tarea.items():
        d, h = calendario.duracion_habil(config, periodos)
        dias_total += d
        horas_total += h
        dias_proyecto[proyecto_de[clave]] += d
        if clave[0] == "t":
            dias_tarea[clave[1]] = d

    def agrupar(campo: str) -> list[ConteoTiempo]:
        grupos: dict[str, list] = defaultdict(lambda: [0, CERO])
        for b, r in en_rango:
            g = grupos[getattr(b, campo)]
            g[0] += 1
            g[1] += calendario.duracion_habil(config, [r])[0]
        return sorted((ConteoTiempo(clave=k, bloqueos=n, dias=d) for k, (n, d) in grupos.items()), key=lambda c: -c.dias)

    cerrados = [b.dias_impacto for b, _ in en_rango if b.fecha_fin_bloqueo is not None and b.dias_impacto is not None]

    # Desfases de las tareas de proyecto en alcance.
    stmt = (
        select(Tarea).options(selectinload(Tarea.reprogramaciones), selectinload(Tarea.usuario), selectinload(Tarea.proyecto))
        .where(Tarea.id_proyecto.is_not(None))
    )
    if ids is not None:
        stmt = stmt.where(Tarea.id_proyecto.in_(ids))
    tareas = list(await db.scalars(stmt))
    origen_de = {b.id_bloqueo: b.responsable_origen for b, _ in filas}
    total = sin_bloqueo = ejecucion = 0
    por_origen: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    desfase_proyecto: dict[int, int] = defaultdict(int)
    con_desfase: list[TareaDesfase] = []
    for t in tareas:
        dias = desfase(config, t, hoy)
        if dias <= 0:
            continue
        # Solo las reprogramaciones posteriores a la última línea base.
        reps = t.reprogramaciones
        ultima_base = max((i for i, r in enumerate(reps) if r.es_linea_base), default=-1)
        reps = [r for r in reps[ultima_base + 1:] if not r.es_linea_base]
        reprogramado = 0
        for r in reps:
            reprogramado += r.dias_habiles
            if r.id_bloqueo is not None and r.id_bloqueo in origen_de:
                por_origen[origen_de[r.id_bloqueo]][0] += 1
                por_origen[origen_de[r.id_bloqueo]][1] += r.dias_habiles
            else:
                sin_bloqueo += r.dias_habiles
        ejecucion += dias - reprogramado
        total += dias
        desfase_proyecto[t.id_proyecto] += dias
        nombres.setdefault(t.id_proyecto, t.proyecto.nombre_proyecto)
        con_desfase.append(TareaDesfase(
            id_tarea=t.id_tarea, titulo=t.titulo, id_proyecto=t.id_proyecto, nombre_proyecto=t.proyecto.nombre_proyecto,
            nombre_usuario=t.usuario.nombre, estado=t.estado, fecha_fin_base=t.fecha_fin_base or t.fecha_fin, fecha_fin=t.fecha_fin,
            desfase_dias=dias, dias_bloqueada=dias_tarea.get(t.id_tarea, CERO),
        ))

    proyectos = set(dias_proyecto) | set(desfase_proyecto) | {b.id_proyecto for b in abiertos}
    return ResumenBloqueos(
        abiertos=len(abiertos),
        abiertos_automaticos=sum(b.automatico for b in abiertos),
        compromisos_vencidos=sum(1 for b in abiertos if b.fecha_compromiso and b.fecha_compromiso < hoy),
        bloqueos_periodo=len(en_rango),
        dias_bloqueo=dias_total.quantize(CERO), horas_bloqueo=horas_total.quantize(CERO),
        promedio_resolucion_dias=(sum(cerrados) / len(cerrados)).quantize(CERO) if cerrados else None,
        tareas_bloqueadas=len({b.id_tarea for b in abiertos if b.id_tarea}),
        por_causa=agrupar("causa_raiz"), por_origen=agrupar("responsable_origen"),
        por_proyecto=sorted(
            (ProyectoBloqueos(
                id_proyecto=i, nombre_proyecto=nombres.get(i, f"#{i}"), abiertos=sum(b.id_proyecto == i for b in abiertos),
                dias=dias_proyecto.get(i, CERO).quantize(CERO), desfase_dias=desfase_proyecto.get(i, 0),
            ) for i in proyectos),
            key=lambda p: (-p.dias, -p.desfase_dias),
        ),
        desfase=DesgloseDesfase(
            total=total, reprogramado_sin_bloqueo=sin_bloqueo, ejecucion=ejecucion,
            por_bloqueo=[ConteoTiempo(clave=k, bloqueos=n, dias=Decimal(d)) for k, (n, d) in sorted(por_origen.items(), key=lambda x: -x[1][1])],
        ),
        tareas_con_desfase=sorted(con_desfase, key=lambda t: -t.desfase_dias)[:15],
    )
