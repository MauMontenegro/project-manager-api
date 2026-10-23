"""Esquema inicial: 17 tablas de la plataforma Petroil

Revision ID: 0001
Revises:
Create Date: 2026-10-06

El SQL está congelado tal como era el esquema en esta revisión. No se genera desde los modelos: si lo hiciera, en una
base vacía crearía las tablas ya en su versión final y las migraciones siguientes fallarían al volver a crearlas.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ESQUEMA = [
    """
CREATE TABLE empresa (
	id_empresa BIGSERIAL NOT NULL,
	nombre_empresa VARCHAR(150) NOT NULL,
	division VARCHAR(100) NOT NULL,
	grupo VARCHAR(100) NOT NULL,
	activo BOOLEAN DEFAULT true NOT NULL,
	fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_empresa PRIMARY KEY (id_empresa),
	CONSTRAINT uq_empresa_nombre_empresa UNIQUE (nombre_empresa)
)
    """,
    """
CREATE TABLE area (
	id_area BIGSERIAL NOT NULL,
	id_empresa BIGINT NOT NULL,
	nombre_area VARCHAR(150) NOT NULL,
	codigo_area VARCHAR(50) NOT NULL,
	CONSTRAINT pk_area PRIMARY KEY (id_area),
	CONSTRAINT fk_area_id_empresa_empresa FOREIGN KEY(id_empresa) REFERENCES empresa (id_empresa) ON DELETE RESTRICT ON UPDATE CASCADE,
	CONSTRAINT uq_area_codigo_area UNIQUE (codigo_area)
)
    """,
    """
CREATE INDEX ix_area_id_empresa ON area (id_empresa)
    """,
    """
CREATE TABLE usuario (
	id_usuario BIGSERIAL NOT NULL,
	id_area BIGINT NOT NULL,
	nombre VARCHAR(150) NOT NULL,
	correo VARCHAR(150) NOT NULL,
	perfil_tecnico VARCHAR(100) NOT NULL,
	capacidad_horas_semanales NUMERIC(5, 2) NOT NULL,
	activo BOOLEAN DEFAULT true NOT NULL,
	CONSTRAINT pk_usuario PRIMARY KEY (id_usuario),
	CONSTRAINT ck_usuario_perfil_tecnico CHECK (perfil_tecnico IN ('Análisis Funcional', 'Backend', 'Frontend', 'Testing', 'Infraestructura', 'Líder', 'Cliente')),
	CONSTRAINT ck_usuario_capacidad_no_negativa CHECK (capacidad_horas_semanales >= 0),
	CONSTRAINT fk_usuario_id_area_area FOREIGN KEY(id_area) REFERENCES area (id_area) ON DELETE RESTRICT ON UPDATE CASCADE,
	CONSTRAINT uq_usuario_correo UNIQUE (correo)
)
    """,
    """
CREATE INDEX ix_usuario_id_area ON usuario (id_area)
    """,
    """
CREATE TABLE solicitud_demanda (
	id_solicitud BIGSERIAL NOT NULL,
	id_usuario_solicitante BIGINT NOT NULL,
	id_empresa BIGINT NOT NULL,
	id_area BIGINT NOT NULL,
	descripcion_necesidad TEXT NOT NULL,
	fecha_solicitud TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	estado_demanda VARCHAR(50) NOT NULL,
	CONSTRAINT pk_solicitud_demanda PRIMARY KEY (id_solicitud),
	CONSTRAINT ck_solicitud_demanda_estado_demanda CHECK (estado_demanda IN ('Solicitado', 'Analizado', 'Priorizado', 'Esperando Capacidad', 'Planeado', 'En Ejecución', 'Rechazado')),
	CONSTRAINT fk_solicitud_demanda_id_usuario_solicitante_usuario FOREIGN KEY(id_usuario_solicitante) REFERENCES usuario (id_usuario) ON DELETE RESTRICT ON UPDATE CASCADE,
	CONSTRAINT fk_solicitud_demanda_id_empresa_empresa FOREIGN KEY(id_empresa) REFERENCES empresa (id_empresa) ON DELETE RESTRICT ON UPDATE CASCADE,
	CONSTRAINT fk_solicitud_demanda_id_area_area FOREIGN KEY(id_area) REFERENCES area (id_area) ON DELETE RESTRICT ON UPDATE CASCADE
)
    """,
    """
CREATE INDEX ix_solicitud_demanda_estado_demanda ON solicitud_demanda (estado_demanda)
    """,
    """
CREATE INDEX ix_solicitud_demanda_id_area ON solicitud_demanda (id_area)
    """,
    """
CREATE INDEX ix_solicitud_demanda_id_empresa ON solicitud_demanda (id_empresa)
    """,
    """
CREATE INDEX ix_solicitud_demanda_id_usuario_solicitante ON solicitud_demanda (id_usuario_solicitante)
    """,
    """
CREATE TABLE proyecto (
	id_proyecto BIGSERIAL NOT NULL,
	id_solicitud BIGINT,
	lider_id BIGINT NOT NULL,
	nombre_proyecto VARCHAR(200) NOT NULL,
	problema_oportunidad TEXT NOT NULL,
	objetivo TEXT NOT NULL,
	alcance TEXT NOT NULL,
	fuera_de_alcance TEXT NOT NULL,
	estado_proyecto VARCHAR(50) NOT NULL,
	fecha_tentativa DATE,
	fecha_comprometida DATE,
	fecha_real_cierre DATE,
	semaforo VARCHAR(20) NOT NULL,
	CONSTRAINT pk_proyecto PRIMARY KEY (id_proyecto),
	CONSTRAINT ck_proyecto_estado_proyecto CHECK (estado_proyecto IN ('Iniciación', 'Planeación', 'Ejecución', 'Cierre', 'Cancelado', 'Pausado')),
	CONSTRAINT ck_proyecto_semaforo CHECK (semaforo IN ('Verde', 'Amarillo', 'Rojo')),
	CONSTRAINT uq_proyecto_id_solicitud UNIQUE (id_solicitud),
	CONSTRAINT fk_proyecto_id_solicitud_solicitud_demanda FOREIGN KEY(id_solicitud) REFERENCES solicitud_demanda (id_solicitud) ON DELETE SET NULL ON UPDATE CASCADE,
	CONSTRAINT fk_proyecto_lider_id_usuario FOREIGN KEY(lider_id) REFERENCES usuario (id_usuario) ON DELETE RESTRICT ON UPDATE CASCADE
)
    """,
    """
CREATE INDEX ix_proyecto_estado_proyecto ON proyecto (estado_proyecto)
    """,
    """
CREATE INDEX ix_proyecto_lider_id ON proyecto (lider_id)
    """,
    """
CREATE INDEX ix_proyecto_semaforo ON proyecto (semaforo)
    """,
    """
CREATE TABLE actualizacion_avance (
	id_actualizacion BIGSERIAL NOT NULL,
	id_proyecto BIGINT NOT NULL,
	id_usuario_registra BIGINT NOT NULL,
	fecha_registro TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	porcentaje_avance NUMERIC(5, 2) NOT NULL,
	resumen_avance TEXT NOT NULL,
	proximo_hito VARCHAR(200),
	riesgo_detectado TEXT,
	CONSTRAINT pk_actualizacion_avance PRIMARY KEY (id_actualizacion),
	CONSTRAINT ck_actualizacion_avance_porcentaje_valido CHECK (porcentaje_avance BETWEEN 0 AND 100),
	CONSTRAINT fk_actualizacion_avance_id_proyecto_proyecto FOREIGN KEY(id_proyecto) REFERENCES proyecto (id_proyecto) ON DELETE CASCADE ON UPDATE CASCADE,
	CONSTRAINT fk_actualizacion_avance_id_usuario_registra_usuario FOREIGN KEY(id_usuario_registra) REFERENCES usuario (id_usuario) ON DELETE RESTRICT ON UPDATE CASCADE
)
    """,
    """
CREATE INDEX ix_actualizacion_avance_fecha_registro ON actualizacion_avance (fecha_registro)
    """,
    """
CREATE INDEX ix_actualizacion_avance_id_proyecto ON actualizacion_avance (id_proyecto)
    """,
    """
CREATE INDEX ix_actualizacion_avance_id_usuario_registra ON actualizacion_avance (id_usuario_registra)
    """,
    """
CREATE TABLE business_case (
	id_business_case BIGSERIAL NOT NULL,
	id_proyecto BIGINT NOT NULL,
	ahorro_estimado NUMERIC(15, 2) DEFAULT '0.00' NOT NULL,
	costo_evitado_estimado NUMERIC(15, 2) DEFAULT '0.00' NOT NULL,
	capacidad_liberada_horas NUMERIC(10, 2) DEFAULT '0.00' NOT NULL,
	incremento_ingreso_estimado NUMERIC(15, 2) DEFAULT '0.00' NOT NULL,
	beneficios_cualitativos TEXT,
	riesgos_cumplimiento TEXT,
	CONSTRAINT pk_business_case PRIMARY KEY (id_business_case),
	CONSTRAINT uq_business_case_id_proyecto UNIQUE (id_proyecto),
	CONSTRAINT fk_business_case_id_proyecto_proyecto FOREIGN KEY(id_proyecto) REFERENCES proyecto (id_proyecto) ON DELETE CASCADE ON UPDATE CASCADE
)
    """,
    """
CREATE TABLE compromiso_cliente (
	id_compromiso BIGSERIAL NOT NULL,
	id_proyecto BIGINT NOT NULL,
	id_area_cliente BIGINT NOT NULL,
	descripcion_actividad TEXT NOT NULL,
	fecha_limite_compromiso DATE NOT NULL,
	fecha_cumplimiento_real DATE,
	estado_compromiso VARCHAR(50) NOT NULL,
	CONSTRAINT pk_compromiso_cliente PRIMARY KEY (id_compromiso),
	CONSTRAINT ck_compromiso_cliente_estado_compromiso CHECK (estado_compromiso IN ('Pendiente', 'Cumplido', 'Vencido', 'Cancelado')),
	CONSTRAINT fk_compromiso_cliente_id_proyecto_proyecto FOREIGN KEY(id_proyecto) REFERENCES proyecto (id_proyecto) ON DELETE CASCADE ON UPDATE CASCADE,
	CONSTRAINT fk_compromiso_cliente_id_area_cliente_area FOREIGN KEY(id_area_cliente) REFERENCES area (id_area) ON DELETE RESTRICT ON UPDATE CASCADE
)
    """,
    """
CREATE INDEX ix_compromiso_cliente_id_area_cliente ON compromiso_cliente (id_area_cliente)
    """,
    """
CREATE INDEX ix_compromiso_cliente_id_proyecto ON compromiso_cliente (id_proyecto)
    """,
    """
CREATE TABLE etapa_proyecto (
	id_etapa BIGSERIAL NOT NULL,
	id_proyecto BIGINT NOT NULL,
	nombre_etapa VARCHAR(100) NOT NULL,
	orden_secuencia INTEGER NOT NULL,
	horas_estimadas NUMERIC(8, 2) NOT NULL,
	horas_efectivas_reales NUMERIC(8, 2) DEFAULT '0.00' NOT NULL,
	fecha_inicio_est DATE,
	fecha_fin_est DATE,
	estado_etapa VARCHAR(50) NOT NULL,
	CONSTRAINT pk_etapa_proyecto PRIMARY KEY (id_etapa),
	CONSTRAINT ck_etapa_proyecto_nombre_etapa CHECK (nombre_etapa IN ('Análisis', 'Arquitectura', 'Desarrollo', 'Testing', 'Implementación')),
	CONSTRAINT ck_etapa_proyecto_estado_etapa CHECK (estado_etapa IN ('Pendiente', 'En Curso', 'Detenido', 'Completado')),
	CONSTRAINT ck_etapa_proyecto_orden_positivo CHECK (orden_secuencia > 0),
	CONSTRAINT ck_etapa_proyecto_horas_estimadas_no_negativas CHECK (horas_estimadas >= 0),
	CONSTRAINT uq_etapa_proyecto_orden UNIQUE (id_proyecto, orden_secuencia),
	CONSTRAINT fk_etapa_proyecto_id_proyecto_proyecto FOREIGN KEY(id_proyecto) REFERENCES proyecto (id_proyecto) ON DELETE CASCADE ON UPDATE CASCADE
)
    """,
    """
CREATE INDEX ix_etapa_proyecto_id_proyecto ON etapa_proyecto (id_proyecto)
    """,
    """
CREATE TABLE evaluacion_financiera (
	id_evaluacion BIGSERIAL NOT NULL,
	id_proyecto BIGINT NOT NULL,
	costo_desarrollo NUMERIC(15, 2) DEFAULT '0.00' NOT NULL,
	costo_implementacion NUMERIC(15, 2) DEFAULT '0.00' NOT NULL,
	costo_consultoria NUMERIC(15, 2) DEFAULT '0.00' NOT NULL,
	costo_licencias NUMERIC(15, 2) DEFAULT '0.00' NOT NULL,
	costo_infraestructura NUMERIC(15, 2) DEFAULT '0.00' NOT NULL,
	costo_horas_internas NUMERIC(15, 2) DEFAULT '0.00' NOT NULL,
	costo_mantenimiento NUMERIC(15, 2) DEFAULT '0.00' NOT NULL,
	inversion_total NUMERIC(15, 2) NOT NULL,
	beneficio_bruto NUMERIC(15, 2) NOT NULL,
	beneficio_neto NUMERIC(15, 2) NOT NULL,
	roi NUMERIC(8, 4) NOT NULL,
	payback_meses NUMERIC(6, 2) NOT NULL,
	relacion_costo_beneficio NUMERIC(8, 4) NOT NULL,
	CONSTRAINT pk_evaluacion_financiera PRIMARY KEY (id_evaluacion),
	CONSTRAINT ck_evaluacion_financiera_inversion_no_negativa CHECK (inversion_total >= 0),
	CONSTRAINT uq_evaluacion_financiera_id_proyecto UNIQUE (id_proyecto),
	CONSTRAINT fk_evaluacion_financiera_id_proyecto_proyecto FOREIGN KEY(id_proyecto) REFERENCES proyecto (id_proyecto) ON DELETE CASCADE ON UPDATE CASCADE
)
    """,
    """
CREATE TABLE proyecto_dependencia (
	id_proyecto_origen BIGINT NOT NULL,
	id_proyecto_dependiente BIGINT NOT NULL,
	tipo_dependencia VARCHAR(50) NOT NULL,
	descripcion_dependencia TEXT,
	CONSTRAINT pk_proyecto_dependencia PRIMARY KEY (id_proyecto_origen, id_proyecto_dependiente),
	CONSTRAINT ck_proyecto_dependencia_tipo_dependencia CHECK (tipo_dependencia IN ('Bloqueante', 'Secuencial', 'Informativa')),
	CONSTRAINT ck_proyecto_dependencia_sin_autodependencia CHECK (id_proyecto_origen <> id_proyecto_dependiente),
	CONSTRAINT fk_proyecto_dependencia_id_proyecto_origen_proyecto FOREIGN KEY(id_proyecto_origen) REFERENCES proyecto (id_proyecto) ON DELETE CASCADE ON UPDATE CASCADE,
	CONSTRAINT fk_proyecto_dependencia_id_proyecto_dependiente_proyecto FOREIGN KEY(id_proyecto_dependiente) REFERENCES proyecto (id_proyecto) ON DELETE CASCADE ON UPDATE CASCADE
)
    """,
    """
CREATE INDEX ix_proyecto_dependencia_id_proyecto_dependiente ON proyecto_dependencia (id_proyecto_dependiente)
    """,
    """
CREATE TABLE proyecto_empresa_impactada (
	id_proyecto BIGINT NOT NULL,
	id_empresa BIGINT NOT NULL,
	nivel_impacto VARCHAR(20) NOT NULL,
	notas_impacto TEXT,
	CONSTRAINT pk_proyecto_empresa_impactada PRIMARY KEY (id_proyecto, id_empresa),
	CONSTRAINT ck_proyecto_empresa_impactada_nivel_impacto CHECK (nivel_impacto IN ('Alto', 'Medio', 'Bajo')),
	CONSTRAINT fk_proyecto_empresa_impactada_id_proyecto_proyecto FOREIGN KEY(id_proyecto) REFERENCES proyecto (id_proyecto) ON DELETE CASCADE ON UPDATE CASCADE,
	CONSTRAINT fk_proyecto_empresa_impactada_id_empresa_empresa FOREIGN KEY(id_empresa) REFERENCES empresa (id_empresa) ON DELETE CASCADE ON UPDATE CASCADE
)
    """,
    """
CREATE INDEX ix_proyecto_empresa_impactada_id_empresa ON proyecto_empresa_impactada (id_empresa)
    """,
    """
CREATE TABLE realizacion_valor (
	id_valor BIGSERIAL NOT NULL,
	id_proyecto BIGINT NOT NULL,
	impacto_estimado NUMERIC(15, 2) NOT NULL,
	impacto_comprometido NUMERIC(15, 2) NOT NULL,
	impacto_aprobado NUMERIC(15, 2) NOT NULL,
	impacto_realizado NUMERIC(15, 2) NOT NULL,
	fecha_validacion DATE NOT NULL,
	observaciones TEXT,
	CONSTRAINT pk_realizacion_valor PRIMARY KEY (id_valor),
	CONSTRAINT fk_realizacion_valor_id_proyecto_proyecto FOREIGN KEY(id_proyecto) REFERENCES proyecto (id_proyecto) ON DELETE CASCADE ON UPDATE CASCADE
)
    """,
    """
CREATE INDEX ix_realizacion_valor_id_proyecto ON realizacion_valor (id_proyecto)
    """,
    """
CREATE TABLE asignacion_recurso (
	id_asignacion BIGSERIAL NOT NULL,
	id_usuario BIGINT NOT NULL,
	id_etapa BIGINT NOT NULL,
	id_proyecto BIGINT NOT NULL,
	perfil_requerido VARCHAR(100) NOT NULL,
	horas_asignadas NUMERIC(8, 2) NOT NULL,
	porcentaje_utilizacion NUMERIC(5, 2) NOT NULL,
	CONSTRAINT pk_asignacion_recurso PRIMARY KEY (id_asignacion),
	CONSTRAINT ck_asignacion_recurso_horas_positivas CHECK (horas_asignadas > 0),
	CONSTRAINT ck_asignacion_recurso_utilizacion_valida CHECK (porcentaje_utilizacion BETWEEN 0 AND 100),
	CONSTRAINT uq_asignacion_usuario_etapa UNIQUE (id_usuario, id_etapa),
	CONSTRAINT fk_asignacion_recurso_id_usuario_usuario FOREIGN KEY(id_usuario) REFERENCES usuario (id_usuario) ON DELETE RESTRICT ON UPDATE CASCADE,
	CONSTRAINT fk_asignacion_recurso_id_etapa_etapa_proyecto FOREIGN KEY(id_etapa) REFERENCES etapa_proyecto (id_etapa) ON DELETE CASCADE ON UPDATE CASCADE,
	CONSTRAINT fk_asignacion_recurso_id_proyecto_proyecto FOREIGN KEY(id_proyecto) REFERENCES proyecto (id_proyecto) ON DELETE CASCADE ON UPDATE CASCADE
)
    """,
    """
CREATE INDEX ix_asignacion_recurso_id_etapa ON asignacion_recurso (id_etapa)
    """,
    """
CREATE INDEX ix_asignacion_recurso_id_proyecto ON asignacion_recurso (id_proyecto)
    """,
    """
CREATE INDEX ix_asignacion_recurso_id_usuario ON asignacion_recurso (id_usuario)
    """,
    """
CREATE TABLE bloqueo_interrupcion (
	id_bloqueo BIGSERIAL NOT NULL,
	id_proyecto BIGINT NOT NULL,
	id_etapa BIGINT NOT NULL,
	causa_raiz VARCHAR(100) NOT NULL,
	responsable_origen VARCHAR(50) NOT NULL,
	fecha_inicio_bloqueo TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	fecha_fin_bloqueo TIMESTAMP WITH TIME ZONE,
	dias_impacto NUMERIC(6, 2),
	CONSTRAINT pk_bloqueo_interrupcion PRIMARY KEY (id_bloqueo),
	CONSTRAINT ck_bloqueo_interrupcion_causa_raiz CHECK (causa_raiz IN ('Cambio de Prioridad', 'Dependencia Externa', 'Falta de Información', 'Recurso Reasignado', 'Incidente Operativo', 'Cambio de Alcance', 'Retrabajo', 'Espera del Cliente', 'Decisión Pendiente')),
	CONSTRAINT ck_bloqueo_interrupcion_responsable_origen CHECK (responsable_origen IN ('DTI', 'Cliente', 'Tercero')),
	CONSTRAINT fk_bloqueo_interrupcion_id_proyecto_proyecto FOREIGN KEY(id_proyecto) REFERENCES proyecto (id_proyecto) ON DELETE CASCADE ON UPDATE CASCADE,
	CONSTRAINT fk_bloqueo_interrupcion_id_etapa_etapa_proyecto FOREIGN KEY(id_etapa) REFERENCES etapa_proyecto (id_etapa) ON DELETE CASCADE ON UPDATE CASCADE
)
    """,
    """
CREATE INDEX ix_bloqueo_interrupcion_causa_raiz ON bloqueo_interrupcion (causa_raiz)
    """,
    """
CREATE INDEX ix_bloqueo_interrupcion_fecha_inicio_bloqueo ON bloqueo_interrupcion (fecha_inicio_bloqueo)
    """,
    """
CREATE INDEX ix_bloqueo_interrupcion_id_etapa ON bloqueo_interrupcion (id_etapa)
    """,
    """
CREATE INDEX ix_bloqueo_interrupcion_id_proyecto ON bloqueo_interrupcion (id_proyecto)
    """,
    """
CREATE TABLE hito_entregable (
	id_hito BIGSERIAL NOT NULL,
	id_proyecto BIGINT NOT NULL,
	id_etapa BIGINT NOT NULL,
	nombre_entregable VARCHAR(200) NOT NULL,
	fecha_comprometida DATE NOT NULL,
	fecha_entrega_real DATE,
	estado_hito VARCHAR(50) NOT NULL,
	CONSTRAINT pk_hito_entregable PRIMARY KEY (id_hito),
	CONSTRAINT ck_hito_entregable_estado_hito CHECK (estado_hito IN ('Pendiente', 'Entregado', 'Aprobado', 'Atrasado')),
	CONSTRAINT fk_hito_entregable_id_proyecto_proyecto FOREIGN KEY(id_proyecto) REFERENCES proyecto (id_proyecto) ON DELETE CASCADE ON UPDATE CASCADE,
	CONSTRAINT fk_hito_entregable_id_etapa_etapa_proyecto FOREIGN KEY(id_etapa) REFERENCES etapa_proyecto (id_etapa) ON DELETE CASCADE ON UPDATE CASCADE
)
    """,
    """
CREATE INDEX ix_hito_entregable_id_etapa ON hito_entregable (id_etapa)
    """,
    """
CREATE INDEX ix_hito_entregable_id_proyecto ON hito_entregable (id_proyecto)
    """,
    """
CREATE TABLE registro_retrabajo (
	id_retrabajo BIGSERIAL NOT NULL,
	id_proyecto BIGINT NOT NULL,
	etapa_origen_id BIGINT NOT NULL,
	etapa_destino_id BIGINT NOT NULL,
	motivo_regreso TEXT NOT NULL,
	causa_raiz_requerimiento TEXT NOT NULL,
	horas_adicionales NUMERIC(8, 2) NOT NULL,
	impacto_dias_fecha INTEGER DEFAULT '0' NOT NULL,
	CONSTRAINT pk_registro_retrabajo PRIMARY KEY (id_retrabajo),
	CONSTRAINT ck_registro_retrabajo_horas_adicionales_no_negativas CHECK (horas_adicionales >= 0),
	CONSTRAINT fk_registro_retrabajo_id_proyecto_proyecto FOREIGN KEY(id_proyecto) REFERENCES proyecto (id_proyecto) ON DELETE CASCADE ON UPDATE CASCADE,
	CONSTRAINT fk_registro_retrabajo_etapa_origen_id_etapa_proyecto FOREIGN KEY(etapa_origen_id) REFERENCES etapa_proyecto (id_etapa) ON DELETE RESTRICT ON UPDATE CASCADE,
	CONSTRAINT fk_registro_retrabajo_etapa_destino_id_etapa_proyecto FOREIGN KEY(etapa_destino_id) REFERENCES etapa_proyecto (id_etapa) ON DELETE RESTRICT ON UPDATE CASCADE
)
    """,
    """
CREATE INDEX ix_registro_retrabajo_etapa_destino_id ON registro_retrabajo (etapa_destino_id)
    """,
    """
CREATE INDEX ix_registro_retrabajo_etapa_origen_id ON registro_retrabajo (etapa_origen_id)
    """,
    """
CREATE INDEX ix_registro_retrabajo_id_proyecto ON registro_retrabajo (id_proyecto)
    """,
]

TABLAS = ['empresa', 'area', 'usuario', 'solicitud_demanda', 'proyecto', 'actualizacion_avance', 'business_case', 'compromiso_cliente', 'etapa_proyecto', 'evaluacion_financiera', 'proyecto_dependencia', 'proyecto_empresa_impactada', 'realizacion_valor', 'asignacion_recurso', 'bloqueo_interrupcion', 'hito_entregable', 'registro_retrabajo']


def upgrade() -> None:
    for sentencia in ESQUEMA:
        op.execute(sentencia)


def downgrade() -> None:
    for tabla in reversed(TABLAS):
        op.drop_table(tabla)
