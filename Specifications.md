
Actúa como un Senior Backend Engineer experto en Python, FastAPI, SQLAlchemy 2.0 y Arquitectura de Software.

Necesito que desarrolles la estructura completa y el código base para el Backend de la "Plataforma Inteligente de Gestión de Proyectos de Petroil", tomando como base el siguiente diseño de base de datos relacional (PostgreSQL en entorno OLTP).

---
### 1. REQUISITOS TÉCNICOS Y STACK DE TECNOLOGÍAS
- **Lenguaje**: Python 3.11+
- **Framework Web**: FastAPI (asíncrono)
- **ORM**: SQLAlchemy 2.0 (utilizando `AsyncSession`, `mapped_column`, `Mapped` y `select`)
- **Driver BD**: `asyncpg` para PostgreSQL
- **Validación y Serialización**: Pydantic v2 (`BaseModel`, `ConfigDict(from_attributes=True)`)
- **Migraciones**: Alembic (configuración asíncrona)
- **Manejo de Variables de Entorno**: `pydantic-settings`
- **Contenedorización**: `docker-compose.yml` para levantar la aplicación y la base de datos PostgreSQL.

---
### 2. MODELO DE DATOS Y TABLAS
El backend debe implementar las siguientes 17 entidades relacionales con sus respectivas relaciones y FKs:
1. **empresa** (`id_empresa`, `nombre_empresa`, `division`, `grupo`, `fecha_creacion`)
2. **area** (`id_area`, `nombre_area`, `id_empresa`)
3. **usuario** (`id_usuario`, `nombre`, `correo`, `id_puesto`, `departamento`, `skills`, `capacidad_horas_semanales`, `activo`) + catálogo **puesto** (`id_puesto`, `nombre_puesto`)
4. **solicitud_demanda** (`id_solicitud`, `descripcion_necesidad`, `fecha_solicitud`, `estado_demanda`, `id_usuario_solicitante`, `id_empresa`, `id_area`)
5. **proyecto** (`id_proyecto`, `nombre_proyecto`, `problema_oportunidad`, `objetivo`, `alcance`, `fuera_de_alcance`, `etapa_actual`, `estado_proyecto`, `porcentaje_avance`, `fecha_tentativa`, `fecha_comprometida`, `fecha_real_cierre`, `semaforo`, `id_solicitud` [UNIQUE], `lider_id`)
6. **business_case** (`id_business_case`, `ahorro_estimado`, `costo_evitado_estimado`, `capacidad_liberada_horas`, `incremento_ingreso_estimado`, `beneficios_cualitativos`, `id_proyecto` [UNIQUE])
7. **evaluacion_financiera** (`id_evaluacion`, `costo_desarrollo`, `costo_implementacion`, `costo_consultoria`, `costo_licencias`, `costo_infraestructura`, `costo_horas_internas`, `costo_mantenimiento`, `inversion_total`, `beneficio_bruto`, `beneficio_neto`, `roi`, `payback`, `relacion_costo_beneficio`, `id_proyecto` [UNIQUE])
8. **etapa_proyecto** (`id_etapa`, `nombre_etapa`, `orden_secuencia`, `horas_estimadas`, `horas_efectivas_reales`, `fecha_inicio_est`, `fecha_fin_est`, `estado_etapa`, `id_proyecto`)
9. **hito_entregable** (`id_hito`, `nombre_entregable`, `fecha_comprometida`, `fecha_entrega_real`, `estado_hito`, `id_proyecto`, `id_etapa`)
10. **bloqueo_interrupcion** (`id_bloqueo`, `causa_raiz`, `responsable_origen`, `fecha_inicio_bloqueo`, `fecha_fin_bloqueo`, `dias_impacto`, `id_proyecto`, `id_etapa`)
11. **registro_retrabajo** (`id_retrabajo`, `motivo_regreso`, `causa_raiz_requerimiento`, `horas_adicionales`, `impacto_dias_fecha`, `id_proyecto`, `etapa_origen_id`, `etapa_destino_id`)
12. **actualizacion_avance** (`id_actualizacion`, `fecha_registro`, `porcentaje_avance`, `resumen_avance`, `proximo_hito`, `riesgo_detectado`, `id_proyecto`, `id_usuario_registra`)
13. **compromiso_cliente** (`id_compromiso`, `descripcion_actividad`, `fecha_limite_compromiso`, `fecha_cumplimiento_real`, `estado_compromiso`, `id_proyecto`, `id_area_cliente`)
14. **realizacion_valor** (`id_valor`, `impacto_estimado`, `impacto_comprometido`, `impacto_aprobado`, `impacto_realizado`, `fecha_validacion`, `id_proyecto`)
15. **asignacion_recurso** (Junction Table M:N: `id_asignacion`, `id_usuario`, `id_etapa`, `id_proyecto`, `perfil_requerido`, `horas_asignadas`, `porcentaje_utilizacion`)
16. **proyecto_empresa_impactada** (Junction Table M:N: PK Compuesta [`id_proyecto`, `id_empresa`], `id_area`, `nivel_impacto`, `notas_impacto`)
17. **proyecto_dependencia** (Junction Table M:N Autorreferenciada: PK Compuesta [`id_proyecto_origen`, `id_proyecto_dependiente`], `tipo_dependencia`, `descripcion_dependencia`)

---
### 3. ESTRUCTURA DEL PROYECTO
Por favor, genera la siguiente estructura modular limpia (Clean Architecture / Domain-Driven layout):

```text
app/
├── core/
│   ├── config.py             # Configuración con pydantic-settings
│   └── database.py           # Engine asíncrono, AsyncSession y Base declarativa
├── models/                   # Modelos de SQLAlchemy 2.0 con Type Annotations
│   ├── __init__.py
│   ├── organizacion.py       # Empresa, Area, Usuario
│   ├── demanda.py            # SolicitudDemanda
│   ├── proyecto.py           # Proyecto, BusinessCase, EvaluacionFinanciera
│   ├── operacion.py          # EtapaProyecto, HitoEntregable, BloqueoInterrupcion, RegistroRetrabajo
│   ├── seguimiento.py        # ActualizacionAvance, CompromisoCliente, RealizacionValor
│   └── tablas_uniones.py     # AsignacionRecurso, ProyectoEmpresaImpactada, ProyectoDependencia
├── schemas/                  # Esquemas de Pydantic v2 (Base, Create, Read, Update)
│   ├── __init__.py
│   ├── proyecto.py
│   ├── usuario.py
│   └── bloqueo.py
├── api/
│   ├── v1/
│   │   ├── endpoints/
│   │   │   ├── proyectos.py  # Endpoints CRUD de proyectos y su ciclo de vida
│   │   │   ├── usuarios.py   # Endpoints CRUD de recursos
│   │   │   └── bloqueos.py   # Registro y gestión de interrupciones
│   │   └── router.py
├── services/                 # Lógica de negocio encapsulada
│   ├── proyecto_service.py
│   └── bloqueo_service.py
└── main.py                   # App FastAPI con middlewares, CORS e inclusión de routers

```

---

### 4. ENTREGABLES REQUERIDOS

1. **Configuración de BD y Sesión Asíncrona**: `app/core/database.py` e `app/core/config.py` con inyección de dependencias `get_db()`.
2. **Modelos ORM (SQLAlchemy 2.0)**: Código completo de las 17 entidades con `Mapped[...]`, `mapped_column(...)`, `ForeignKey` y relaciones bidireccionales (`relationship`).
3. **Esquemas Pydantic v2**: Muestra los schemas principales para `Proyecto`, `Usuario` y `BloqueoInterrupcion` (Create, Response, Update).
4. **Endpoints CRUD Asíncronos**: Muestra controladores completos en FastAPI para los flujos principales (Crear proyecto, Asignar recursos, Registrar un bloqueo/interrupción con cálculo de días y Consultar el portafolio con filtros por semáforo y empresa).
5. **Archivo** **docker-compose.yml** **y** **requirements.txt**: Para poder ejecutar el proyecto con un solo comando.

Escribe código completo, sintácticamente correcto, sin omitir partes ni dejar comentarios del tipo `# TODO: implementar aquí`.