"""Espacios por departamento, etiquetas y proyectos conjuntos

- `plantilla_etapa`: etapas configurables por departamento, sembradas con las cinco macro-etapas.
- `etapa_proyecto`: + descripcion, + estados_permitidos (copia de la plantilla); sin CHECK de nombre.
- `proyecto`: + departamento (se toma del líder), + es_conjunto, + id_proyecto_padre;
  `etapa_actual` admite nulo (conjuntos) y deja de estar restringida a las cinco macro-etapas.
- `etiqueta` y `proyecto_etiqueta`: catálogo de tipos de proyecto por departamento.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEPARTAMENTOS = ("Infraestructura", "Procesos", "Desarrollo de Software")
EN_DEPARTAMENTOS = "departamento IN ({})".format(", ".join(f"'{d}'" for d in DEPARTAMENTOS))

# Copia fija de app.models.ciclo_vida.MACRO_ETAPAS al momento de esta migración.
MACRO_ETAPAS = (
    ("Análisis y Viabilidad", ("Sin Iniciar", "Activo", "En Revisión", "Cancelado"),
     'Se define el "Qué": levantamientos, requerimientos, viabilidad.'),
    ("Diseño y Planificación", ("Activo", "En Revisión", "Pausado", "Cancelado"),
     'Se define el "Cómo": arquitectura, cronogramas, flujos To-Be.'),
    ("Construcción y Ejecución", ("Activo", "Pausado", "Bloqueado", "Cancelado"),
     "Se construye: programar, instalar hardware, redactar manuales."),
    ("Pruebas y Validación", ("Activo", "En Revisión", "Bloqueado", "Cancelado"),
     "Se valida: QA, UAT, pruebas de estrés, simulaciones."),
    ("Despliegue y Cierre", ("Activo", "Completado"),
     "Se lanza y finaliza: Go-Live, encendido, capacitación, cierre."),
)


def upgrade() -> None:
    op.create_table(
        "plantilla_etapa",
        sa.Column("id_plantilla", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("departamento", sa.String(50), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("descripcion", sa.Text()),
        sa.Column("estados_permitidos", ARRAY(sa.String(50)), nullable=False),
        sa.CheckConstraint(EN_DEPARTAMENTOS, name="departamento"),
        sa.CheckConstraint("orden > 0", name="orden_positivo"),
    )
    op.create_index("uq_plantilla_etapa_departamento_orden", "plantilla_etapa", ["departamento", "orden"], unique=True)
    op.create_index(
        "uq_plantilla_etapa_departamento_nombre", "plantilla_etapa", ["departamento", sa.text("lower(nombre)")],
        unique=True,
    )
    plantilla = sa.table(
        "plantilla_etapa", sa.column("departamento"), sa.column("orden"), sa.column("nombre"),
        sa.column("descripcion"), sa.column("estados_permitidos", ARRAY(sa.String(50))),
    )
    op.bulk_insert(plantilla, [
        {"departamento": d, "orden": i, "nombre": nombre, "descripcion": desc, "estados_permitidos": list(estados)}
        for d in DEPARTAMENTOS
        for i, (nombre, estados, desc) in enumerate(MACRO_ETAPAS, start=1)
    ])

    op.add_column("etapa_proyecto", sa.Column("descripcion", sa.Text()))
    op.add_column("etapa_proyecto", sa.Column("estados_permitidos", ARRAY(sa.String(50))))
    for nombre, estados, desc in MACRO_ETAPAS:
        op.execute(
            sa.text("UPDATE etapa_proyecto SET descripcion = :d, estados_permitidos = :e WHERE nombre_etapa = :n")
            .bindparams(sa.bindparam("e", type_=ARRAY(sa.String(50))), d=desc, e=list(estados), n=nombre)
        )
    op.execute("UPDATE etapa_proyecto SET estados_permitidos = ARRAY['Activo'] WHERE estados_permitidos IS NULL")
    op.alter_column("etapa_proyecto", "estados_permitidos", nullable=False)
    op.drop_constraint("nombre_etapa", "etapa_proyecto", type_="check")

    op.drop_constraint("etapa_actual", "proyecto", type_="check")
    op.alter_column("proyecto", "etapa_actual", nullable=True)
    op.add_column("proyecto", sa.Column("departamento", sa.String(50)))
    op.add_column("proyecto", sa.Column("es_conjunto", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column(
        "proyecto",
        sa.Column(
            "id_proyecto_padre", sa.BigInteger(),
            sa.ForeignKey(
                "proyecto.id_proyecto", name="fk_proyecto_id_proyecto_padre_proyecto",
                ondelete="RESTRICT", onupdate="CASCADE",
            ),
        ),
    )
    op.create_index("ix_proyecto_departamento", "proyecto", ["departamento"])
    op.create_index("ix_proyecto_id_proyecto_padre", "proyecto", ["id_proyecto_padre"])
    op.create_check_constraint("departamento", "proyecto", EN_DEPARTAMENTOS)
    op.create_check_constraint(
        "conjunto_valido", "proyecto",
        "NOT es_conjunto OR (departamento IS NULL AND id_proyecto_padre IS NULL AND etapa_actual IS NULL)",
    )
    op.create_check_constraint(
        "subproyecto_con_departamento", "proyecto", "id_proyecto_padre IS NULL OR departamento IS NOT NULL"
    )
    # Los proyectos existentes toman el departamento de su líder; los de Dirección quedan sin asignar.
    op.execute(
        "UPDATE proyecto p SET departamento = u.departamento FROM usuario u "
        f"WHERE u.id_usuario = p.lider_id AND u.{EN_DEPARTAMENTOS}"
    )

    op.create_table(
        "etiqueta",
        sa.Column("id_etiqueta", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("departamento", sa.String(50), nullable=False),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
        sa.CheckConstraint(EN_DEPARTAMENTOS, name="departamento"),
        sa.CheckConstraint("color ~ '^#[0-9a-fA-F]{6}$'", name="color_hex"),
    )
    op.create_index("ix_etiqueta_departamento", "etiqueta", ["departamento"])
    op.create_index(
        "uq_etiqueta_departamento_nombre", "etiqueta", ["departamento", sa.text("lower(nombre)")], unique=True
    )
    op.create_table(
        "proyecto_etiqueta",
        sa.Column(
            "id_proyecto", sa.BigInteger(),
            sa.ForeignKey("proyecto.id_proyecto", name="fk_proyecto_etiqueta_id_proyecto_proyecto",
                          ondelete="CASCADE", onupdate="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "id_etiqueta", sa.BigInteger(),
            sa.ForeignKey("etiqueta.id_etiqueta", name="fk_proyecto_etiqueta_id_etiqueta_etiqueta",
                          ondelete="CASCADE", onupdate="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("ix_proyecto_etiqueta_id_etiqueta", "proyecto_etiqueta", ["id_etiqueta"])


def downgrade() -> None:
    op.drop_table("proyecto_etiqueta")
    op.drop_table("etiqueta")

    # Los conjuntos no existían: se borran (sus subproyectos quedan como proyectos normales).
    op.execute("UPDATE proyecto SET id_proyecto_padre = NULL")
    op.execute("DELETE FROM proyecto WHERE es_conjunto")
    op.drop_constraint("subproyecto_con_departamento", "proyecto", type_="check")
    op.drop_constraint("conjunto_valido", "proyecto", type_="check")
    op.drop_constraint("departamento", "proyecto", type_="check")
    op.drop_index("ix_proyecto_id_proyecto_padre", "proyecto")
    op.drop_index("ix_proyecto_departamento", "proyecto")
    op.drop_column("proyecto", "id_proyecto_padre")
    op.drop_column("proyecto", "es_conjunto")
    op.drop_column("proyecto", "departamento")
    nombres = ", ".join(f"'{n}'" for n, _, _ in MACRO_ETAPAS)
    op.alter_column("proyecto", "etapa_actual", nullable=False)
    op.create_check_constraint("etapa_actual", "proyecto", f"etapa_actual IN ({nombres})")

    op.create_check_constraint("nombre_etapa", "etapa_proyecto", f"nombre_etapa IN ({nombres})")
    op.drop_column("etapa_proyecto", "estados_permitidos")
    op.drop_column("etapa_proyecto", "descripcion")

    op.drop_table("plantilla_etapa")
