"""Ciclo de vida por macro-etapas: etapa actual + estatus + avance

- `proyecto`: + etapa_actual, + porcentaje_avance; `estado_proyecto` pasa de las fases
  (Iniciación, Planeación, Ejecución, Cierre, Pausado, Cancelado) al estatus de la etapa
  (Sin Iniciar, Activo, En Revisión, Pausado, Bloqueado, Cancelado, Completado).
- `etapa_proyecto`: todos los proyectos quedan con las cinco macro-etapas, orden 1–5.
  Las etapas antiguas se renombran conservando su id (y con él asignaciones, bloqueos,
  hitos y retrabajos): Análisis → 1, Arquitectura → 2, Desarrollo → 3, Testing → 4,
  Implementación → 5. Si un proyecto tenía dos etapas con el mismo nombre se fusionan.
  Las que falten se crean. El estatus de cada etapa se deriva del proyecto.

Igual que 0002 y 0003: 0001 crea el esquema desde los modelos vigentes, así que en una
base nueva los pasos de datos no encuentran nada que convertir.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ETAPAS = ["Análisis y Viabilidad", "Diseño y Planificación", "Construcción y Ejecución", "Pruebas y Validación", "Despliegue y Cierre"]
ETAPAS_ANTIGUAS = ["Análisis", "Arquitectura", "Desarrollo", "Testing", "Implementación"]
ESTATUS = ["Sin Iniciar", "Activo", "En Revisión", "Pausado", "Bloqueado", "Cancelado", "Completado"]
ESTADOS_ANTIGUOS = ["Iniciación", "Planeación", "Ejecución", "Cierre", "Cancelado", "Pausado"]
ESTADOS_ETAPA_ANTIGUOS = ["Pendiente", "En Curso", "Detenido", "Completado"]
AVANCE_DESDE = [0, 16, 31, 76, 91]

# Estado anterior → (orden de la etapa, estatus). Pausado y Cancelado toman la etapa más
# avanzada que se hubiera iniciado, limitada a las etapas donde ese estatus es válido.
FASE_ANTIGUA = {
    "Iniciación": (1, "Activo"),
    "Planeación": (2, "Activo"),
    "Ejecución": (3, "Activo"),
    "Cierre": (5, "Completado"),
}
RANGO_POR_ESTATUS = {"Pausado": (2, 3), "Cancelado": (1, 4)}


def _en(columna: str, valores: list[str]) -> str:
    return f"{columna} IN ({', '.join(repr(v) for v in valores)})"


def _cambiar_checks(etapas: list[str], estatus_proyecto: list[str], estatus_etapa: list[str]) -> None:
    for tabla, nombre in [
        ("proyecto", "estado_proyecto"), ("proyecto", "etapa_actual"),
        ("etapa_proyecto", "nombre_etapa"), ("etapa_proyecto", "estado_etapa"),
    ]:
        op.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS ck_{tabla}_{nombre}")
    op.create_check_constraint("estado_proyecto", "proyecto", _en("estado_proyecto", estatus_proyecto))
    op.create_check_constraint("nombre_etapa", "etapa_proyecto", _en("nombre_etapa", etapas))
    op.create_check_constraint("estado_etapa", "etapa_proyecto", _en("estado_etapa", estatus_etapa))


def _fusionar_etapa(conn, conservar: int, duplicada: int) -> None:
    """Mueve todo lo que cuelga de `duplicada` a `conservar` y la elimina."""
    # Una persona asignada a ambas: se suman horas a la asignación que se conserva.
    conn.execute(sa.text(
        "UPDATE asignacion_recurso a SET horas_asignadas = a.horas_asignadas + d.horas_asignadas"
        " FROM asignacion_recurso d WHERE a.id_etapa = :c AND d.id_etapa = :d AND a.id_usuario = d.id_usuario"
    ), {"c": conservar, "d": duplicada})
    conn.execute(sa.text(
        "DELETE FROM asignacion_recurso d USING asignacion_recurso a"
        " WHERE d.id_etapa = :d AND a.id_etapa = :c AND a.id_usuario = d.id_usuario"
    ), {"c": conservar, "d": duplicada})
    for tabla, columna in [
        ("asignacion_recurso", "id_etapa"), ("bloqueo_interrupcion", "id_etapa"), ("hito_entregable", "id_etapa"),
        ("registro_retrabajo", "etapa_origen_id"), ("registro_retrabajo", "etapa_destino_id"),
    ]:
        conn.execute(sa.text(f"UPDATE {tabla} SET {columna} = :c WHERE {columna} = :d"), {"c": conservar, "d": duplicada})
    conn.execute(sa.text(
        "UPDATE etapa_proyecto c SET horas_estimadas = c.horas_estimadas + d.horas_estimadas,"
        " horas_efectivas_reales = c.horas_efectivas_reales + d.horas_efectivas_reales,"
        " fecha_inicio_est = LEAST(c.fecha_inicio_est, d.fecha_inicio_est),"
        " fecha_fin_est = GREATEST(c.fecha_fin_est, d.fecha_fin_est)"
        " FROM etapa_proyecto d WHERE c.id_etapa = :c AND d.id_etapa = :d"
    ), {"c": conservar, "d": duplicada})
    conn.execute(sa.text("DELETE FROM etapa_proyecto WHERE id_etapa = :d"), {"d": duplicada})


def upgrade() -> None:
    conn = op.get_bind()
    columnas = {c["name"] for c in sa.inspect(conn).get_columns("proyecto")}

    for tabla, nombre in [
        ("proyecto", "estado_proyecto"), ("etapa_proyecto", "nombre_etapa"), ("etapa_proyecto", "estado_etapa"),
    ]:
        op.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS ck_{tabla}_{nombre}")
    if "etapa_actual" not in columnas:
        op.add_column("proyecto", sa.Column("etapa_actual", sa.String(100), nullable=True))
        op.create_index("ix_proyecto_etapa_actual", "proyecto", ["etapa_actual"])
    if "porcentaje_avance" not in columnas:
        op.add_column(
            "proyecto", sa.Column("porcentaje_avance", sa.Numeric(5, 2), nullable=False, server_default="0.00")
        )
        op.create_check_constraint("porcentaje_avance_valido", "proyecto", "porcentaje_avance BETWEEN 0 AND 100")

    proyectos = conn.execute(sa.text("SELECT id_proyecto, estado_proyecto FROM proyecto")).all()
    for id_proyecto, estado in proyectos:
        etapas = conn.execute(sa.text(
            "SELECT id_etapa, nombre_etapa, estado_etapa FROM etapa_proyecto"
            " WHERE id_proyecto = :p ORDER BY orden_secuencia, id_etapa"
        ), {"p": id_proyecto}).all()

        # 1. Una etapa por macro-etapa (la primera de cada nombre; el resto se fusiona en ella).
        por_orden: dict[int, int] = {}
        iniciadas = [0]
        for id_etapa, nombre, estado_etapa in etapas:
            orden = ETAPAS_ANTIGUAS.index(nombre) + 1 if nombre in ETAPAS_ANTIGUAS else ETAPAS.index(nombre) + 1
            if estado_etapa in ("En Curso", "Detenido", "Completado", "Activo", "Bloqueado", "En Revisión"):
                iniciadas.append(orden)
            if orden in por_orden:
                _fusionar_etapa(conn, por_orden[orden], id_etapa)
            else:
                por_orden[orden] = id_etapa

        # 2. Etapa actual, estatus y avance del proyecto.
        if estado in FASE_ANTIGUA:
            orden_actual, estatus = FASE_ANTIGUA[estado]
        elif estado in RANGO_POR_ESTATUS:
            minimo, maximo = RANGO_POR_ESTATUS[estado]
            orden_actual, estatus = min(max(max(iniciadas), minimo), maximo), estado
        else:  # ya convertido
            continue
        avance = 100 if estatus == "Completado" else AVANCE_DESDE[orden_actual - 1]
        conn.execute(sa.text(
            "UPDATE proyecto SET etapa_actual = :e, estado_proyecto = :s, porcentaje_avance = :a WHERE id_proyecto = :p"
        ), {"e": ETAPAS[orden_actual - 1], "s": estatus, "a": avance, "p": id_proyecto})

        # 3. Renombra y reordena (el desplazamiento evita choques con uq_etapa_proyecto_orden) y crea las que falten.
        conn.execute(sa.text(
            "UPDATE etapa_proyecto SET orden_secuencia = orden_secuencia + 1000 WHERE id_proyecto = :p"
        ), {"p": id_proyecto})
        for orden, nombre in enumerate(ETAPAS, start=1):
            estatus_etapa = "Completado" if orden < orden_actual else estatus if orden == orden_actual else "Sin Iniciar"
            valores = {"n": nombre, "o": orden, "s": estatus_etapa, "p": id_proyecto}
            if orden in por_orden:
                conn.execute(sa.text(
                    "UPDATE etapa_proyecto SET nombre_etapa = :n, orden_secuencia = :o, estado_etapa = :s"
                    " WHERE id_etapa = :id"
                ), {**valores, "id": por_orden[orden]})
            else:
                conn.execute(sa.text(
                    "INSERT INTO etapa_proyecto (id_proyecto, nombre_etapa, orden_secuencia, horas_estimadas, estado_etapa)"
                    " VALUES (:p, :n, :o, 0, :s)"
                ), valores)

    op.execute(f"UPDATE proyecto SET etapa_actual = '{ETAPAS[0]}' WHERE etapa_actual IS NULL")
    op.alter_column("proyecto", "etapa_actual", nullable=False)
    _cambiar_checks(ETAPAS, ESTATUS, ESTATUS)
    op.create_check_constraint("etapa_actual", "proyecto", _en("etapa_actual", ETAPAS))


def downgrade() -> None:
    # Conversión aproximada: En Revisión y Bloqueado vuelven a la fase de su etapa; el avance se pierde.
    for tabla, nombre in [
        ("proyecto", "estado_proyecto"), ("proyecto", "etapa_actual"),
        ("etapa_proyecto", "nombre_etapa"), ("etapa_proyecto", "estado_etapa"),
    ]:
        op.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS ck_{tabla}_{nombre}")
    op.execute(
        "UPDATE proyecto SET estado_proyecto = CASE"
        " WHEN estado_proyecto IN ('Pausado', 'Cancelado') THEN estado_proyecto"
        " WHEN estado_proyecto = 'Completado' THEN 'Cierre'"
        f" WHEN etapa_actual = '{ETAPAS[0]}' THEN 'Iniciación'"
        f" WHEN etapa_actual = '{ETAPAS[1]}' THEN 'Planeación'"
        " ELSE 'Ejecución' END"
    )
    op.execute(
        "UPDATE etapa_proyecto SET estado_etapa = CASE estado_etapa"
        " WHEN 'Sin Iniciar' THEN 'Pendiente' WHEN 'Completado' THEN 'Completado'"
        " WHEN 'Activo' THEN 'En Curso' WHEN 'En Revisión' THEN 'En Curso' ELSE 'Detenido' END"
    )
    for nuevo, antiguo in zip(ETAPAS, ETAPAS_ANTIGUAS):
        op.execute(f"UPDATE etapa_proyecto SET nombre_etapa = '{antiguo}' WHERE nombre_etapa = '{nuevo}'")
    op.drop_column("proyecto", "porcentaje_avance")  # arrastra su CHECK y, abajo, el índice
    op.drop_column("proyecto", "etapa_actual")
    _cambiar_checks(ETAPAS_ANTIGUAS, ESTADOS_ANTIGUOS, ESTADOS_ETAPA_ANTIGUOS)
