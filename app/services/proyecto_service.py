from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.core.security import Actor, exigir
from app.models.demanda import SolicitudDemanda
from app.models.ciclo_vida import ESTADOS_FINALES
from app.models.departamento import Etiqueta
from app.models.enums import DepartamentoProyecto, EstadoDemanda, EstadoProyecto, Semaforo, TipoRecurso
from app.models.operacion import EtapaProyecto, RegistroRetrabajo, Tarea
from app.models.organizacion import Area, Empresa, Usuario
from app.models.proyecto import Proyecto
from app.models.tablas_uniones import AsignacionRecurso, ProyectoEmpresaImpactada
from app.services import (
    auditoria_service, avance_service, conjunto_service, configuracion_service, departamento_service,
    equipo_trabajo_service, semaforo_service, tarea_service,
)
from app.schemas.proyecto import (
    AsignacionCreate,
    AsignacionRead,
    EmpresaImpactadaIn,
    EtapaUpdate,
    ProyectoCambioEstado,
    ProyectoCreate,
    ProyectoUpdate,
    SubproyectoIn,
)

MSG_GESTION = "Solo el líder del proyecto, el Gerente de su departamento o el Administrador pueden modificarlo"
MSG_CONJUNTO = "Un proyecto conjunto no tiene etapas propias: se gestiona en sus subproyectos"
CAMPOS_CONSOLIDADOS = {"fecha_inicio", "fecha_tentativa", "fecha_comprometida", "horas_presupuestadas"}


async def _usuario_activo(db: AsyncSession, id_usuario: int, rol: str) -> Usuario:
    usuario = await db.get(Usuario, id_usuario)
    if usuario is None:
        raise NotFoundError(f"{rol} con id {id_usuario} no existe")
    if not usuario.activo:
        raise BusinessRuleError(f"{rol} con id {id_usuario} está inactivo")
    if rol == "Líder" and usuario.tipo_recurso == TipoRecurso.ACTIVO.value:
        raise BusinessRuleError(f"'{usuario.nombre}' es un activo y no puede liderar proyectos")
    return usuario


def _opciones_lectura() -> list:
    """Lo que necesitan ProyectoRead / ProyectoDetalle sin cargas perezosas."""
    return [
        selectinload(Proyecto.etiquetas),
        selectinload(Proyecto.subproyectos).selectinload(Proyecto.etiquetas),
    ]


async def obtener_proyecto(db: AsyncSession, id_proyecto: int) -> Proyecto:
    stmt = (
        select(Proyecto)
        .where(Proyecto.id_proyecto == id_proyecto)
        .options(selectinload(Proyecto.empresas_impactadas), selectinload(Proyecto.padre), *_opciones_lectura())
        .execution_options(populate_existing=True)
    )
    proyecto = await db.scalar(stmt)
    if proyecto is None:
        raise NotFoundError(f"Proyecto con id {id_proyecto} no existe")
    proyecto.horas_en_tareas = await tarea_service.horas_en_tareas(db, id_proyecto)
    return proyecto


async def _validar_empresas_impactadas(db: AsyncSession, empresas: list[EmpresaImpactadaIn]) -> None:
    """Las empresas y áreas deben existir y cada área debe pertenecer a su empresa."""
    ids_empresas = {e.id_empresa for e in empresas}
    if not ids_empresas:
        return
    encontradas = set(await db.scalars(select(Empresa.id_empresa).where(Empresa.id_empresa.in_(ids_empresas))))
    faltantes = ids_empresas - encontradas
    if faltantes:
        raise NotFoundError(f"Empresas inexistentes: {sorted(faltantes)}")

    ids_areas = {e.id_area for e in empresas}
    empresa_de_area = dict(
        (await db.execute(select(Area.id_area, Area.id_empresa).where(Area.id_area.in_(ids_areas)))).all()
    )
    faltantes = ids_areas - empresa_de_area.keys()
    if faltantes:
        raise NotFoundError(f"Áreas inexistentes: {sorted(faltantes)}")
    for e in empresas:
        if empresa_de_area[e.id_area] != e.id_empresa:
            raise BusinessRuleError(f"El área {e.id_area} no pertenece a la empresa {e.id_empresa}")


async def _etiquetas_validas(db: AsyncSession, ids: list[int], departamentos: list[str]) -> list[Etiqueta]:
    """Las etiquetas deben existir y ser de alguno de los departamentos del proyecto."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    etiquetas = list(await db.scalars(select(Etiqueta).where(Etiqueta.id_etiqueta.in_(ids))))
    faltantes = set(ids) - {e.id_etiqueta for e in etiquetas}
    if faltantes:
        raise NotFoundError(f"Etiquetas inexistentes: {sorted(faltantes)}")
    ajenas = [e.nombre for e in etiquetas if e.departamento not in departamentos]
    if ajenas:
        donde = ", ".join(departamentos) if departamentos else "ningún departamento (asígnale uno primero)"
        raise BusinessRuleError(f"Las etiquetas {', '.join(ajenas)} no son de {donde}")
    return etiquetas


def _departamentos(proyecto: Proyecto) -> list[str]:
    if proyecto.es_conjunto:
        return [h.departamento for h in proyecto.subproyectos]
    return [proyecto.departamento] if proyecto.departamento else []


async def _nuevo_proyecto(db: AsyncSession, departamento: DepartamentoProyecto, **campos: Any) -> Proyecto:
    """Proyecto de un departamento en su primera etapa, con las etapas de la plantilla vigente."""
    plantilla = await departamento_service.plantilla(db, departamento)
    proyecto = Proyecto(
        **campos,
        departamento=departamento.value,
        etapa_actual=plantilla[0].nombre,
        estado_proyecto=EstadoProyecto.SIN_INICIAR.value,
        porcentaje_avance=Decimal("0.00"),
        horas_presupuestadas_manual=campos.get("horas_presupuestadas") is not None,
    )
    await configuracion_service.aplicar_presupuesto(db, proyecto)
    proyecto.etapas = [
        EtapaProyecto(
            nombre_etapa=e.nombre, orden_secuencia=e.orden, descripcion=e.descripcion,
            estados_permitidos=list(e.estados_permitidos), horas_estimadas=Decimal("0.00"),
            estado_etapa=EstadoProyecto.SIN_INICIAR.value,
        )
        for e in plantilla
    ]
    return proyecto


def _datos_subproyecto(padre: Proyecto | ProyectoCreate, sub: SubproyectoIn) -> dict[str, Any]:
    return {
        "nombre_proyecto": f"{padre.nombre_proyecto} · {sub.departamento.value}"[:200],
        "lider_id": sub.lider_id,
        **{c: getattr(padre, c) for c in (
            "id_equipo_trabajo", "problema_oportunidad", "objetivo", "alcance", "fuera_de_alcance",
            "fecha_inicio", "fecha_tentativa", "fecha_comprometida",
        )},
    }


async def crear_proyecto(db: AsyncSession, actor: Actor, data: ProyectoCreate) -> Proyecto:
    if data.es_conjunto:
        exigir(actor.gestiona_equipo, "Solo los Gerentes o el Administrador pueden crear proyectos conjuntos")
    else:
        exigir(
            actor.crea_proyectos_en(data.departamento),
            f"Solo el Gerente o un Líder de {data.departamento}, o el Administrador, pueden crear proyectos en ese departamento",
        )
    await _usuario_activo(db, data.lider_id, "Líder")
    for sub in data.subproyectos:
        await _usuario_activo(db, sub.lider_id, "Líder")

    solicitud: SolicitudDemanda | None = None
    if data.id_solicitud is not None:
        solicitud = await db.get(SolicitudDemanda, data.id_solicitud)
        if solicitud is None:
            raise NotFoundError(f"Solicitud con id {data.id_solicitud} no existe")
        ya_usada = await db.scalar(select(Proyecto.id_proyecto).where(Proyecto.id_solicitud == data.id_solicitud))
        if ya_usada is not None:
            raise ConflictError(f"La solicitud {data.id_solicitud} ya está asociada al proyecto {ya_usada}")

    await _validar_empresas_impactadas(db, data.empresas_impactadas)
    if data.id_equipo_trabajo is not None:
        await equipo_trabajo_service.existe(db, data.id_equipo_trabajo)
    fin = data.fecha_comprometida or data.fecha_tentativa
    if data.fecha_inicio and fin and fin < data.fecha_inicio:
        raise BusinessRuleError("La fecha de inicio del proyecto no puede ser posterior a su fecha de fin")

    departamentos = [s.departamento.value for s in data.subproyectos] if data.es_conjunto else [data.departamento.value]
    etiquetas = await _etiquetas_validas(db, data.etiquetas, departamentos)
    campos = data.model_dump(exclude={"empresas_impactadas", "subproyectos", "etiquetas", "departamento", "es_conjunto"})

    if data.es_conjunto:
        campos.pop("horas_presupuestadas")  # se consolida de los subproyectos
        proyecto = Proyecto(
            **campos, es_conjunto=True, etapa_actual=None, estado_proyecto=EstadoProyecto.SIN_INICIAR.value,
            porcentaje_avance=Decimal("0.00"), horas_presupuestadas_manual=False,
        )
        for sub in data.subproyectos:
            hijo = await _nuevo_proyecto(db, sub.departamento, **_datos_subproyecto(data, sub))
            hijo.etiquetas = [e for e in etiquetas if e.departamento == sub.departamento]
            hijo.padre = proyecto
    else:
        proyecto = await _nuevo_proyecto(db, data.departamento, **campos)

    proyecto.empresas_impactadas = [ProyectoEmpresaImpactada(**e.model_dump()) for e in data.empresas_impactadas]
    proyecto.etiquetas = etiquetas
    db.add(proyecto)

    if solicitud is not None:
        solicitud.estado_demanda = EstadoDemanda.EN_EJECUCION.value

    await db.flush()
    # Solo un conjunto tiene la colección en memoria; en uno normal accederla dispararía una carga perezosa.
    for hijo in proyecto.subproyectos if data.es_conjunto else []:
        await semaforo_service.recalcular(db, hijo)
    await semaforo_service.recalcular(db, proyecto)
    await db.commit()
    return await obtener_proyecto(db, proyecto.id_proyecto)


async def actualizar_proyecto(db: AsyncSession, actor: Actor, id_proyecto: int, data: ProyectoUpdate) -> Proyecto:
    proyecto = await obtener_proyecto(db, id_proyecto)
    exigir(actor.gestiona_proyecto(proyecto), MSG_GESTION)
    cambios = data.model_dump(exclude_unset=True)

    for campo in ("nombre_proyecto", "problema_oportunidad", "objetivo", "alcance", "fuera_de_alcance", "lider_id",
                  "departamento", "etiquetas"):
        if campo in cambios and cambios[campo] is None:
            raise BusinessRuleError(f"{campo} no puede ser nulo")

    if proyecto.es_conjunto and (CAMPOS_CONSOLIDADOS | {"departamento"}) & cambios.keys():
        raise BusinessRuleError(
            "Las fechas y el presupuesto de un proyecto conjunto se calculan a partir de sus subproyectos"
        )

    if "lider_id" in cambios:
        await _usuario_activo(db, cambios["lider_id"], "Líder")

    if "id_equipo_trabajo" in cambios and cambios["id_equipo_trabajo"] != proyecto.id_equipo_trabajo:
        if proyecto.id_proyecto_padre is not None:
            raise BusinessRuleError("Un subproyecto pertenece al equipo de trabajo de su conjunto: cámbialo en el conjunto")
        if cambios["id_equipo_trabajo"] is not None:
            await equipo_trabajo_service.existe(db, cambios["id_equipo_trabajo"])
        for hijo in proyecto.subproyectos if proyecto.es_conjunto else []:
            hijo.id_equipo_trabajo = cambios["id_equipo_trabajo"]

    if "departamento" in cambios:
        nuevo = cambios.pop("departamento").value
        if nuevo != proyecto.departamento:
            if proyecto.id_proyecto_padre is not None:
                raise BusinessRuleError("El departamento de un subproyecto no se puede cambiar")
            exigir(
                actor.es_admin or (actor.gestiona_equipo and actor.departamento == nuevo),
                f"Solo el Gerente de {nuevo} o el Administrador pueden mover proyectos a ese departamento",
            )
            proyecto.departamento = nuevo
            if "etiquetas" not in cambios:  # las del departamento anterior dejan de aplicar
                proyecto.etiquetas = [e for e in proyecto.etiquetas if e.departamento == nuevo]

    if "etiquetas" in cambios:
        proyecto.etiquetas = await _etiquetas_validas(db, cambios.pop("etiquetas"), _departamentos(proyecto))

    if "empresas_impactadas" in cambios:
        cambios.pop("empresas_impactadas")
        if data.empresas_impactadas is None:
            raise BusinessRuleError("empresas_impactadas no puede ser nulo; envía [] para quitarlas todas")
        await _validar_empresas_impactadas(db, data.empresas_impactadas)
        # Se actualizan en sitio las que siguen (la PK es proyecto + empresa), se agregan las nuevas
        # y delete-orphan borra las que ya no vienen.
        actuales = {e.id_empresa: e for e in proyecto.empresas_impactadas}
        nuevas = []
        for e in data.empresas_impactadas:
            fila = actuales.get(e.id_empresa) or ProyectoEmpresaImpactada(id_empresa=e.id_empresa)
            fila.id_area, fila.nivel_impacto, fila.notas_impacto = e.id_area, e.nivel_impacto.value, e.notas_impacto
            nuevas.append(fila)
        proyecto.empresas_impactadas = nuevas

    for campo, valor in cambios.items():
        setattr(proyecto, campo, valor)
    if not proyecto.es_conjunto:
        if "horas_presupuestadas" in cambios:  # con valor se fija a mano; null vuelve al cálculo automático
            proyecto.horas_presupuestadas_manual = cambios["horas_presupuestadas"] is not None
        await configuracion_service.aplicar_presupuesto(db, proyecto)
        if CAMPOS_CONSOLIDADOS & cambios.keys():
            await tarea_service.validar_proyecto_contra_tareas(db, proyecto)

    await semaforo_service.recalcular(db, proyecto)
    await db.commit()
    return await obtener_proyecto(db, id_proyecto)


async def _borrar(db: AsyncSession, proyecto: Proyecto) -> None:
    """Borra un proyecto (no conjunto) con todo lo que cuelga de él. Si venía de una solicitud de
    demanda, esta vuelve a 'Planeado' para poder originar otro proyecto."""
    if proyecto.id_solicitud is not None:
        solicitud = await db.get(SolicitudDemanda, proyecto.id_solicitud)
        if solicitud is not None and solicitud.estado_demanda == EstadoDemanda.EN_EJECUCION.value:
            solicitud.estado_demanda = EstadoDemanda.PLANEADO.value
    # Los retrabajos apuntan a etapas con RESTRICT: se borran antes que la cascada llegue a las etapas.
    await db.execute(delete(RegistroRetrabajo).where(RegistroRetrabajo.id_proyecto == proyecto.id_proyecto))
    await db.delete(proyecto)


async def eliminar_proyecto(db: AsyncSession, actor: Actor, id_proyecto: int) -> None:
    """Borrado definitivo con todo lo que cuelga del proyecto. Un conjunto se borra con sus subproyectos."""
    exigir(actor.es_admin, "Solo el Administrador puede eliminar proyectos")
    proyecto = await obtener_proyecto(db, id_proyecto)

    for hijo in proyecto.subproyectos:
        await _borrar(db, hijo)
    await db.flush()
    auditoria_service.registrar(
        db, actor, entidad="proyecto", id_entidad=id_proyecto, accion="baja",
        resumen=f"Proyecto «{proyecto.nombre_proyecto}» eliminado",
    )
    await _borrar(db, proyecto)
    if proyecto.id_proyecto_padre is not None:
        await conjunto_service.consolidar(db, await db.get(Proyecto, proyecto.id_proyecto_padre))
    await db.commit()


async def agregar_subproyecto(db: AsyncSession, actor: Actor, id_proyecto: int, data: SubproyectoIn) -> Proyecto:
    """Suma un departamento al conjunto: su subproyecto toma los textos y fechas del conjunto y las
    etapas de la plantilla del departamento."""
    padre = await obtener_proyecto(db, id_proyecto)
    if not padre.es_conjunto:
        raise BusinessRuleError("Solo un proyecto conjunto tiene subproyectos")
    exigir(
        actor.gestiona_proyecto(padre) or (actor.gestiona_equipo and actor.departamento == data.departamento),
        "Solo el líder del conjunto, el Gerente del departamento que se suma o el Administrador pueden hacerlo",
    )
    if EstadoProyecto(padre.estado_proyecto) in ESTADOS_FINALES:
        raise BusinessRuleError(f"El proyecto está '{padre.estado_proyecto}' y ya no admite cambios")
    if data.departamento.value in _departamentos(padre):
        raise ConflictError(f"{data.departamento.value} ya participa en este proyecto")
    await _usuario_activo(db, data.lider_id, "Líder")

    hijo = await _nuevo_proyecto(db, data.departamento, **_datos_subproyecto(padre, data))
    hijo.id_proyecto_padre = padre.id_proyecto
    db.add(hijo)
    await semaforo_service.recalcular(db, hijo)
    await db.commit()
    return await obtener_proyecto(db, id_proyecto)


async def quitar_subproyecto(db: AsyncSession, actor: Actor, id_proyecto: int, id_subproyecto: int) -> Proyecto:
    """Quita un departamento del conjunto; solo si su subproyecto aún no tiene tareas."""
    padre = await obtener_proyecto(db, id_proyecto)
    exigir(actor.gestiona_proyecto(padre), "Solo el líder del conjunto o el Administrador pueden quitar departamentos")
    hijo = next((h for h in padre.subproyectos if h.id_proyecto == id_subproyecto), None)
    if hijo is None:
        raise NotFoundError(f"El proyecto {id_subproyecto} no es subproyecto de {id_proyecto}")
    if len(padre.subproyectos) <= 1:
        raise BusinessRuleError("Un proyecto conjunto debe conservar al menos un departamento")
    if await db.scalar(select(func.count()).where(Tarea.id_proyecto == id_subproyecto)):
        raise BusinessRuleError(f"El subproyecto de {hijo.departamento} ya tiene tareas y no se puede quitar")

    padre.etiquetas = [e for e in padre.etiquetas if e.departamento != hijo.departamento]
    auditoria_service.registrar(
        db, actor, entidad="proyecto", id_entidad=id_subproyecto, accion="baja",
        resumen=f"{hijo.departamento} deja el proyecto conjunto «{padre.nombre_proyecto}»",
    )
    await _borrar(db, hijo)
    await conjunto_service.consolidar(db, padre)
    await db.commit()
    return await obtener_proyecto(db, id_proyecto)


async def _etapas(db: AsyncSession, id_proyecto: int) -> list[EtapaProyecto]:
    return list(await db.scalars(
        select(EtapaProyecto).where(EtapaProyecto.id_proyecto == id_proyecto).order_by(EtapaProyecto.orden_secuencia)
    ))


async def cambiar_estado(db: AsyncSession, actor: Actor, id_proyecto: int, data: ProyectoCambioEstado) -> Proyecto:
    """Cambio manual de ciclo (el avance lo calculan las tareas, ver avance_service):
    - Un proyecto `Completado` o `Cancelado` ya no admite cambios.
    - Se avanza de una etapa a la siguiente; se puede regresar a cualquier etapa anterior (retrabajo).
    - El estatus debe estar entre los permitidos por la etapa destino (al cambiar de etapa, por defecto `Activo`).
    - `Completado` fija `fecha_real_cierre` y el avance en 100 %."""
    proyecto = await obtener_proyecto(db, id_proyecto)
    exigir(actor.gestiona_proyecto(proyecto), MSG_GESTION)
    if proyecto.es_conjunto:
        raise BusinessRuleError(MSG_CONJUNTO)
    estado_actual = EstadoProyecto(proyecto.estado_proyecto)
    if estado_actual in ESTADOS_FINALES:
        raise BusinessRuleError(f"El proyecto está '{estado_actual.value}' y ya no admite cambios de ciclo")

    etapas = await _etapas(db, id_proyecto)
    nombres = [e.nombre_etapa for e in etapas]
    i_origen = nombres.index(proyecto.etapa_actual) if proyecto.etapa_actual in nombres else 0
    if data.etapa_actual is not None and data.etapa_actual not in nombres:
        raise BusinessRuleError(f"'{data.etapa_actual}' no es una etapa de este proyecto")
    i_destino = nombres.index(data.etapa_actual) if data.etapa_actual else i_origen
    if i_destino > i_origen + 1:
        raise BusinessRuleError(f"Solo se puede avanzar a la siguiente etapa: '{nombres[i_origen + 1]}'")
    destino = etapas[i_destino]

    estado = data.estado_proyecto or (estado_actual if i_destino == i_origen else EstadoProyecto.ACTIVO)
    if estado.value not in destino.estados_permitidos:
        permitidos = ", ".join(destino.estados_permitidos)
        raise BusinessRuleError(
            f"El estatus '{estado.value}' no está permitido en '{destino.nombre_etapa}'. Permitidos: {permitidos}"
        )

    proyecto.etapa_actual = destino.nombre_etapa
    proyecto.estado_proyecto = estado.value
    if estado == EstadoProyecto.COMPLETADO:
        proyecto.fecha_real_cierre = data.fecha_real_cierre or date.today()

    await avance_service.recalcular(db, proyecto, por_tareas=False)
    await db.commit()
    return await obtener_proyecto(db, id_proyecto)


def _filtros(
    p: Any, *, semaforo: Semaforo | None, id_empresa: int | None, estado: EstadoProyecto | None,
    etapa: str | None, lider_id: int | None, etiquetas: list[int] | None,
) -> list:
    """Condiciones sobre `p` (Proyecto o un alias). Una empresa se considera vinculada a un proyecto si es
    una de las empresas impactadas o si es la empresa solicitante de la demanda de origen."""
    filtros = []
    if semaforo is not None:
        filtros.append(p.semaforo == semaforo.value)
    if estado is not None:
        filtros.append(p.estado_proyecto == estado.value)
    if etapa is not None:
        filtros.append(p.etapa_actual == etapa)
    if lider_id is not None:
        filtros.append(p.lider_id == lider_id)
    if id_empresa is not None:
        filtros.append(
            or_(
                p.empresas_impactadas.any(ProyectoEmpresaImpactada.id_empresa == id_empresa),
                p.solicitud.has(SolicitudDemanda.id_empresa == id_empresa),
            )
        )
    if etiquetas:
        filtros.append(p.etiquetas.any(Etiqueta.id_etiqueta.in_(etiquetas)))
    return filtros


async def listar_portafolio(
    db: AsyncSession,
    *,
    departamento: DepartamentoProyecto | None = None,
    semaforo: Semaforo | None = None,
    id_empresa: int | None = None,
    estado: EstadoProyecto | None = None,
    etapa: str | None = None,
    lider_id: int | None = None,
    etiquetas: list[int] | None = None,
    id_equipo_trabajo: int | None = None,
    limit: int = 50,
    offset: int = 0,
    visibles: Any = None,
) -> tuple[list[Proyecto], int]:
    """Portafolio de primer nivel: proyectos normales y conjuntos (con sus subproyectos anidados).

    Con `departamento`, el espacio de ese departamento: sus proyectos y los conjuntos en que participa.
    Un conjunto cumple cada filtro si lo cumple él o alguno de sus subproyectos (del departamento, si se indica);
    `etiquetas` cumple si tiene cualquiera de ellas. `visibles`: condición de visibilidad del rol (un conjunto se ve
    entero o no se ve)."""
    hijo = aliased(Proyecto)
    de_hijo = [hijo.id_proyecto_padre == Proyecto.id_proyecto]
    if departamento is not None:
        de_hijo.append(hijo.departamento == departamento.value)

    filtros = [Proyecto.id_proyecto_padre.is_(None)]
    if visibles is not None:
        filtros.append(visibles)
    if id_equipo_trabajo is not None:  # los subproyectos comparten el de su conjunto
        filtros.append(Proyecto.id_equipo_trabajo == id_equipo_trabajo)
    if departamento is not None:
        filtros.append(or_(Proyecto.departamento == departamento.value, exists().where(*de_hijo)))
    criterios = dict(
        semaforo=semaforo, id_empresa=id_empresa, estado=estado, etapa=etapa, lider_id=lider_id, etiquetas=etiquetas,
    )
    propios, de_hijos = _filtros(Proyecto, **criterios), _filtros(hijo, **criterios)
    filtros += [
        or_(propio, and_(Proyecto.es_conjunto, exists().where(*de_hijo, en_hijo)))
        for propio, en_hijo in zip(propios, de_hijos)
    ]

    total = await db.scalar(select(func.count()).select_from(Proyecto).where(*filtros))
    result = await db.scalars(
        select(Proyecto).where(*filtros).options(*_opciones_lectura())
        .order_by(Proyecto.id_proyecto.desc()).limit(limit).offset(offset)
    )
    return list(result), total or 0


async def actualizar_etapa(
    db: AsyncSession, actor: Actor, id_proyecto: int, id_etapa: int, data: EtapaUpdate
) -> EtapaProyecto:
    exigir(actor.gestiona_proyecto(await obtener_proyecto(db, id_proyecto)), MSG_GESTION)
    etapa = await db.get(EtapaProyecto, id_etapa)
    if etapa is None or etapa.id_proyecto != id_proyecto:
        raise NotFoundError(f"La etapa {id_etapa} no existe en el proyecto {id_proyecto}")

    cambios = data.model_dump(exclude_unset=True)
    if "horas_estimadas" in cambios and cambios["horas_estimadas"] is None:
        raise BusinessRuleError("horas_estimadas no puede ser nulo")
    for campo, valor in cambios.items():
        setattr(etapa, campo, valor)
    if etapa.fecha_inicio_est and etapa.fecha_fin_est and etapa.fecha_fin_est < etapa.fecha_inicio_est:
        raise BusinessRuleError("fecha_fin_est no puede ser anterior a fecha_inicio_est")

    await semaforo_service.recalcular(db, await obtener_proyecto(db, id_proyecto))
    await db.commit()
    await db.refresh(etapa)
    return etapa


async def listar_etapas(db: AsyncSession, id_proyecto: int) -> list[EtapaProyecto]:
    await obtener_proyecto(db, id_proyecto)
    return await _etapas(db, id_proyecto)


async def _con_horas_en_tareas(db: AsyncSession, asignaciones: list[AsignacionRecurso]) -> list[AsignacionRead]:
    """Agrega a cada asignación las horas estimadas de las tareas de esa persona en esa etapa."""
    etapas = {a.id_etapa for a in asignaciones}
    filas = await db.execute(
        select(Tarea.id_usuario, Tarea.id_etapa, func.sum(Tarea.horas_asignadas))
        .where(Tarea.id_etapa.in_(etapas))
        .group_by(Tarea.id_usuario, Tarea.id_etapa)
    ) if etapas else []
    horas = {(u, e): h for u, e, h in filas}
    return [
        AsignacionRead.model_validate(a).model_copy(update={"horas_en_tareas": horas.get((a.id_usuario, a.id_etapa), Decimal(0))})
        for a in asignaciones
    ]


async def asignar_recurso(db: AsyncSession, actor: Actor, id_proyecto: int, data: AsignacionCreate) -> AsignacionRead:
    proyecto = await obtener_proyecto(db, id_proyecto)
    exigir(
        actor.gestiona_proyecto(proyecto),
        "Solo el líder del proyecto, el Gerente de su departamento o el Administrador pueden asignar recursos",
    )
    if EstadoProyecto(proyecto.estado_proyecto) in ESTADOS_FINALES:
        raise BusinessRuleError(f"No se pueden asignar recursos a un proyecto en estado '{proyecto.estado_proyecto}'")

    etapa = await db.get(EtapaProyecto, data.id_etapa)
    if etapa is None or etapa.id_proyecto != id_proyecto:
        raise NotFoundError(f"La etapa {data.id_etapa} no existe en el proyecto {id_proyecto}")

    usuario = await _usuario_activo(db, data.id_usuario, "Usuario")

    duplicada = await db.scalar(
        select(AsignacionRecurso.id_asignacion).where(
            AsignacionRecurso.id_usuario == data.id_usuario, AsignacionRecurso.id_etapa == data.id_etapa
        )
    )
    if duplicada is not None:
        raise ConflictError(f"El usuario {data.id_usuario} ya está asignado a la etapa {data.id_etapa}")

    asignacion = AsignacionRecurso(id_proyecto=id_proyecto, **data.model_dump())
    db.add(asignacion)
    await db.flush()
    auditoria_service.registrar(
        db, actor, entidad="asignacion", id_entidad=asignacion.id_asignacion, id_usuario_afectado=usuario.id_usuario,
        accion="alta",
        resumen=f"Asignado a «{proyecto.nombre_proyecto}» · {etapa.nombre_etapa} como {data.perfil_requerido}",
    )
    await db.commit()
    await db.refresh(asignacion)
    return (await _con_horas_en_tareas(db, [asignacion]))[0]


async def listar_asignaciones(db: AsyncSession, id_proyecto: int) -> list[AsignacionRead]:
    await obtener_proyecto(db, id_proyecto)
    result = await db.scalars(
        select(AsignacionRecurso).where(AsignacionRecurso.id_proyecto == id_proyecto).order_by(AsignacionRecurso.id_asignacion)
    )
    return await _con_horas_en_tareas(db, list(result))
