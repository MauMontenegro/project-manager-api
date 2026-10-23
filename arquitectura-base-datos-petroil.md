# Especificación de Arquitectura y Diseño de Base de Datos: Plataforma Inteligente Petroil

## 1. Marco Arquitectónico y Carga de Trabajo Operacional

El diseño de la base de datos para la **Plataforma Inteligente de Gestión, Productividad y Valor de Proyectos** de Petroil (Dirección de Tecnologías e Innovación - DTI) sintetiza los principios de diseño relacional formal enunciados por **Adrienne Watt** con los patrones de arquitectura de sistemas de datos intensivos expuestos por **Martin Kleppmann**.

> **Flujo Arquitectónico de Datos**: La capa de cliente (Dashboards, Aplicaciones Web/Móviles y Agentes de IA) interactúa de forma directa con un esquema relacional estricto en Tercera Forma Normal (3NF) configurado como *Schema-on-Write*. Las escrituras y transacciones operativas son procesadas por un motor **OLTP** de baja latencia, mientras que la analítica histórica y masiva se transmite asíncronamente mediante **Captura de Datos Cambiados (CDC / Log-Tailing)** hacia un almacén de datos **OLAP** aislado.

### 1.1. Caracterización de Carga de Trabajo (OLTP vs. OLAP)
El núcleo operativo de la plataforma está clasificado como un sistema de **Procesamiento de Transacciones en Línea (OLTP)**. Sus patrones de acceso se caracterizan por escrituras y lecturas puntuales de baja latencia ejecutadas por usuarios concurrentes (líderes de proyecto, analistas, ejecutivos).

*   **Procesamiento OLTP Transaccional**: Optimizado para operaciones interactivas como la actualización de avances en menos de 60 segundos, el registro de bloqueos e interrupciones, la asignación de recursos y la gestión de compromisos. Se prioriza la consistencia estricta, la integridad referencial declarativa y los tiempos de respuesta mínimos en el camino crítico.
*   **Aislamiento del Análisis OLAP**: El cálculo masivo de indicadores de portafolio históricos (tendencias de productividad, métricas consolidadas de *First Time Right* y análisis cualitativos multidimensionales) se desacopla del motor transaccional. La información se transfiere mediante **Captura de Datos Cambiados (CDC / Log-Tailing)** o tuberías ETL hacia un almacén de datos (*Data Warehouse*) relacional con esquema en estrella (*Star Schema*).

### 1.2. Esquema Estricto en Escritura (*Schema-on-Write*) y Desfase de Impedancia
A diferencia de los almacenes de documentos que emplean estructuras flexibles (*schema-on-read*), el motor relacional implementa un esquema estricto en escritura (*schema-on-write*). Esta decisión responde a la necesidad de garantizar la integridad del negocio mediante restricciones declarativas no anulables (`NOT NULL`), claves foráneas (`FOREIGN KEY`) y validaciones explícitas (`CHECK`).

Para resolver el **Desfase de Impedancia Objeto-Relacional (*Object-Relational Mismatch*)**, las entidades del dominio representadas como objetos complejos en las capas de aplicación (un proyecto con sus fases, costos, hitos e interrupciones) se fragmentan (*shredding*) en relaciones normalizadas. Esto elimina la redundancia de datos y permite modelar relaciones Muchos-a-Muchos ($M:N$) de forma transparente sin incurrir en duplicación estructural.

### 1.3. Arquitectura de Tres Niveles de Abstracción
Siguiendo el estándar ANSI/SPARC detallado por Watt, la arquitectura separa los niveles de abstracción:

1.  **Nivel Conceptual/Lógico**: Definición abstracta e independiente de la tecnología sobre entidades, atributos, relaciones y reglas de integridad de negocio.
2.  **Nivel Interno/Físico**: Estructuración técnica de tablas en almacenamiento relacional, índices B-Tree, particionamiento e integridad referencial nativa.
3.  **Nivel Externo (Vistas de Usuario)**: Capa de vistas conceptuales personalizadas según el rol (Dirección, Gerencia, Líder de Proyecto, Cliente Interno).

---

## 2. Modelo Conceptual de Datos (Entidad-Relación)

El modelo conceptual clasifica las entidades de negocio según su fuerza existencial e independencia relacional.

*   **Nivel de Gobernanza y Organización (Kernels)**: Las entidades `Empresa`, `Area` y `Usuario` actúan como la columna vertebral del sistema, proporcionando el marco organizacional y el catálogo de recursos humanos.
*   **Nivel de Demanda y Proyectos Centrales**: La entidad `SolicitudDemanda` evoluciona hacia la entidad principal `Proyecto`, la cual orquesta la totalidad del ciclo de vida.
*   **Nivel de Evaluación Financiera y Valor**: Vinculado al proyecto $1:1$, comprende las entidades `BusinessCase` y `EvaluacionFinanciera`, además del seguimiento temporal en `RealizacionValor`.
*   **Nivel de Ejecución, Calidad y Operación**: El proyecto se desglosa funcionalmente en `EtapaProyecto`, la cual contiene `HitoEntregable`, `BloqueoInterrupcion` y `RegistroRetrabajo`, registrando además `ActualizacionAvance` y `CompromisoCliente`.
*   **Nivel Asociativo ($M:N$)**: Tablas intermedias de vinculación como `AsignacionRecurso`, `ProyectoEmpresaImpactada` y `ProyectoDependencia`.

### 2.1. Entidades Kernel (Independientes)
Constituyen los bloques fundamentales (*building blocks*) del sistema. Existen por sí mismas y sus claves primarias son simples y no derivadas.

*   **Empresa**: Representa las filiales y entidades legales pertenecientes al grupo empresarial.
    *   *Atributos clave*: `id_empresa`, `nombre_empresa`, `division`, `grupo`, `activo`.
*   **Usuario**: Colaboradores operativos de las áreas de negocio y recursos técnicos de DTI (Analistas, Desarrolladores, Testers, Arquitectos).
    *   *Atributos clave*: `id_usuario`, `nombre`, `correo`, `id_puesto`, `departamento`, `skills`, `capacidad_horas_semanales`, `activo`.

### 2.2. Entidades Dependientes y Características
Entidades cuyo significado e identificación presuponen la existencia de una entidad padre o extienden detalles del ciclo de vida.

*   **Area**: Unidad departamental interna de una empresa.
    *   *Atributos clave*: `id_area`, `id_empresa`, `nombre_area`, `codigo_area`.
*   **SolicitudDemanda**: Captura inicial de necesidades funcionales previa a la formalización del proyecto.
    *   *Atributos clave*: `id_solicitud`, `id_usuario_solicitante`, `id_empresa`, `id_area`, `descripcion_necesidad`, `fecha_solicitud`, `estado_demanda`.
*   **Proyecto**: Registro maestro de la iniciativa aprobada y en ejecución.
    *   *Atributos clave*: `id_proyecto`, `id_solicitud`, `lider_id`, `nombre_proyecto`, `problema_oportunidad`, `objetivo`, `alcance`, `fuera_de_alcance`, `etapa_actual`, `estado_proyecto`, `porcentaje_avance`, `fecha_tentativa`, `fecha_comprometida`, `fecha_real_cierre`, `semaforo`.
*   **BusinessCase**: Justificación cualitativa y cuantitativa de beneficios esperados.
    *   *Atributos clave*: `id_business_case`, `id_proyecto`, `ahorro_estimado`, `costo_evitado_estimado`, `capacidad_liberada_horas`, `incremento_ingreso_estimado`, `beneficios_cualitativos`, `riesgos_cumplimiento`.
*   **EvaluacionFinanciera**: Modelo estricto de costos e indicadores de retorno de inversión.
    *   *Atributos clave*: `id_evaluacion`, `id_proyecto`, `costo_desarrollo`, `costo_implementacion`, `costo_consultoria`, `costo_licencias`, `costo_infraestructura`, `costo_horas_internas`, `costo_mantenimiento`, `inversion_total`, `beneficio_bruto`, `beneficio_neto`, `roi`, `payback_meses`, `relacion_costo_beneficio`.
*   **EtapaProyecto**: Desglose secuencial de fases metodológicas.
    *   *Atributos clave*: `id_etapa`, `id_proyecto`, `nombre_etapa`, `orden_secuencia`, `horas_estimadas`, `horas_efectivas_reales`, `fecha_inicio_est`, `fecha_fin_est`, `estado_etapa`.
*   **HitoEntregable**: Compromisos específicos y fechas límite de entrega.
    *   *Atributos clave*: `id_hito`, `id_proyecto`, `id_etapa`, `nombre_entregable`, `fecha_comprometida`, `fecha_entrega_real`, `estado_hito`.
*   **BloqueoInterrupcion**: Registro de eventos de paro, causas raíz y tiempos muertos.
    *   *Atributos clave*: `id_bloqueo`, `id_proyecto`, `id_etapa`, `causa_raiz`, `responsable_origen`, `fecha_inicio_bloqueo`, `fecha_fin_bloqueo`, `dias_impacto`.
*   **RegistroRetrabajo**: Log de devoluciones entre etapas para auditar calidad (*First Time Right*).
    *   *Atributos clave*: `id_retrabajo`, `id_proyecto`, `etapa_origen_id`, `etapa_destino_id`, `motivo_regreso`, `causa_raiz_requerimiento`, `horas_adicionales`, `impacto_dias_fecha`.
*   **ActualizacionAvance**: Bitácora periódica de estado reportada por el líder de proyecto.
    *   *Atributos clave*: `id_actualizacion`, `id_proyecto`, `id_usuario_registra`, `fecha_registro`, `porcentaje_avance`, `resumen_avance`, `proximo_hito`, `riesgo_detectado`.
*   **CompromisoCliente**: Tareas, homologaciones y validaciones a cargo del cliente interno.
    *   *Atributos clave*: `id_compromiso`, `id_proyecto`, `id_area_cliente`, `descripcion_actividad`, `fecha_limite_compromiso`, `fecha_cumplimiento_real`, `estado_compromiso`.
*   **RealizacionValor**: Evaluación temporal del impacto económico capturado post-implementación.
    *   *Atributos clave*: `id_valor`, `id_proyecto`, `impacto_estimado`, `impacto_comprometido`, `impacto_aprobado`, `impacto_realizado`, `fecha_validacion`, `observaciones`.

### 2.3. Entidades Asociativas / Relacionales (Junction Tables)
Resuelven la interconexión Muchos-a-Muchos ($M:N$) entre entidades principales.

*   **AsignacionRecurso**: Conecta usuarios técnicos con etapas de proyectos especificando esfuerzo y utilización.
*   **ProyectoEmpresaImpactada**: Asocia un proyecto con múltiples empresas beneficiarias.
*   **ProyectoDependencia**: Relación autorreferenciada que vincula proyectos bloqueantes con proyectos dependientes.

---

## 3. Modelo Lógico y Diccionario de Datos Completo

Especificación formal de tablas, columnas, tipos de datos PostgreSQL/ANSI SQL, nulidad, claves primarias, claves foráneas y restricciones del sistema.

### 3.1. Tabla: `empresa`
Entidad Kernel que almacena las unidades de negocio del grupo empresarial.

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_empresa` | `BIGINT` | No | `PK` | Identificador único de la empresa. |
| `nombre_empresa` | `VARCHAR(150)` | No | `UNIQUE` | Nombre legal o comercial de la empresa. |
| `division` | `VARCHAR(100)` | No | — | División operativa (ej. Combustibles, Turismo). |
| `grupo` | `VARCHAR(100)` | No | — | Conglomerado corporativo al que pertenece. |
| `activo` | `BOOLEAN` | No | `DEFAULT true` | Estado operativo de la empresa. |

### 3.2. Tabla: `area`
Estructura organizacional dependiente de `empresa`.

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_area` | `BIGINT` | No | `PK` | Identificador único del área. |
| `id_empresa` | `BIGINT` | No | `FK -> empresa(id_empresa)` | Empresa a la que pertenece el área. |
| `nombre_area` | `VARCHAR(150)` | No | — | Nombre del departamento u oficina. |
| `codigo_area` | `VARCHAR(50)` | No | `UNIQUE` | Código alfanumérico institucional. |

### 3.3. Tabla: `usuario`
Catálogo de usuarios del sistema y recursos asignables de DTI.

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_usuario` | `BIGINT` | No | `PK` | Identificador único del usuario. |
| `id_puesto` | `BIGINT` | Sí* | `FK -> puesto(id_puesto)` | Puesto en la empresa (catálogo administrable). |
| `departamento` | `VARCHAR(50)` | Sí* | `CHECK (departamento IN ('Dirección', 'Infraestructura', 'Procesos', 'Desarrollo de Software'))` | Área de la DTI a la que pertenece. |
| `nombre` | `VARCHAR(150)` | No | — | Nombre completo del usuario. |
| `correo` | `VARCHAR(150)` | No | `UNIQUE` | Correo electrónico institucional. |
| `skills` | `VARCHAR(50)[]` | No | `DEFAULT '{}'` | Etiquetas de habilidades (Python, Redes, ITIL…). |
| `capacidad_horas_semanales` | `NUMERIC(5,2)` | No | `CHECK (capacidad_horas_semanales >= 0)` | Horas semanales disponibles de trabajo. |
| `activo` | `BOOLEAN` | No | `DEFAULT true` | Indicador de cuenta activa. |

\* Nulos solo en registros anteriores a la migración 0002; la API los exige al crear.

**Tabla `puesto`** — catálogo de puestos de la DTI: `id_puesto` (`BIGINT`, PK), `nombre_puesto` (`VARCHAR(100)`, `UNIQUE`). Un puesto no puede eliminarse mientras alguna persona lo tenga asignado (`ON DELETE RESTRICT`).

**Equipo (migración 0003)**
- `usuario` añade: `tipo_recurso` (`Interno`/`Externo`/`Activo`), `id_jefe` (FK a `usuario`, `ON DELETE SET NULL`, sin ciclos ni autorreferencia), `rol` (`Director`/`Gerente`/`Colaborador`), `porcentaje_proyectos` (0–100, default 100), `costo_hora`, `proveedor`, `fecha_fin_contrato`. `correo` pasa a ser opcional (activos).
- `skill` (`id_skill`, `nombre` UNIQUE) y `usuario_skill` (PK `id_usuario`+`id_skill`, `nivel` `Básico`/`Intermedio`/`Experto`); reemplazan el arreglo `usuario.skills`.
- `ausencia` (`id_usuario`, `tipo`, `fecha_inicio`, `fecha_fin` ≥ inicio, `nota`).
- `bitacora` (append-only): `fecha`, `id_actor`, `actor_nombre`, `entidad`, `id_entidad`, `id_usuario_afectado`, `accion`, `resumen`, `cambios` JSONB.

### 3.4. Tabla: `solicitud_demanda`
Fase preliminar de captura de iniciativas.

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_solicitud` | `BIGINT` | No | `PK` | Identificador único de la solicitud. |
| `id_usuario_solicitante` | `BIGINT` | No | `FK -> usuario(id_usuario)` | Usuario que registra la necesidad. |
| `id_empresa` | `BIGINT` | No | `FK -> empresa(id_empresa)` | Empresa solicitante principal. |
| `id_area` | `BIGINT` | No | `FK -> area(id_area)` | Área solicitante principal. |
| `descripcion_necesidad` | `TEXT` | No | — | Redacción detallada del requerimiento. |
| `fecha_solicitud` | `TIMESTAMPTZ` | No | `DEFAULT CURRENT_TIMESTAMP` | Fecha y hora de captura. |
| `estado_demanda` | `VARCHAR(50)` | No | `CHECK (estado_demanda IN ('Solicitado', 'Analizado', 'Priorizado', 'Esperando Capacidad', 'Planeado', 'En Ejecución', 'Rechazado'))` | Fase en el flujo de demanda. |

### 3.5. Tabla: `proyecto`
Registro maestro de iniciativas aprobadas.

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_proyecto` | `BIGINT` | No | `PK` | Identificador único del proyecto. |
| `id_solicitud` | `BIGINT` | Sí | `FK -> solicitud_demanda(id_solicitud)`, `UNIQUE` | Solicitud de origen (si aplica). |
| `lider_id` | `BIGINT` | No | `FK -> usuario(id_usuario)` | Líder de DTI asignado al proyecto. |
| `nombre_proyecto` | `VARCHAR(200)` | No | — | Título formal de la iniciativa. |
| `problema_oportunidad` | `TEXT` | No | — | Diagnóstico de origen. |
| `objetivo` | `TEXT` | No | — | Meta cuantitativa o cualitativa. |
| `alcance` | `TEXT` | No | — | Inclusiones explícitas del proyecto. |
| `fuera_de_alcance` | `TEXT` | No | — | Exclusiones explícitas del proyecto. |
| `etapa_actual` | `VARCHAR(100)` | No | `CHECK (etapa_actual IN ('Análisis y Viabilidad', 'Diseño y Planificación', 'Construcción y Ejecución', 'Pruebas y Validación', 'Despliegue y Cierre'))` | Macro-etapa actual del ciclo de vida. |
| `estado_proyecto` | `VARCHAR(50)` | No | `CHECK (estado_proyecto IN ('Sin Iniciar', 'Activo', 'En Revisión', 'Pausado', 'Bloqueado', 'Cancelado', 'Completado'))` | Estatus ("salud") en la etapa actual; los permitidos dependen de la etapa. |
| `porcentaje_avance` | `NUMERIC(5,2)` | No | `CHECK (porcentaje_avance BETWEEN 0 AND 100)`, default `0` | Debe caer en el rango de la etapa actual. |
| `fecha_tentativa` | `DATE` | Sí | — | Estimación inicial antes del análisis. |
| `fecha_comprometida` | `DATE` | Sí | — | Fecha pactada tras capacidad y alcance. |
| `fecha_real_cierre` | `DATE` | Sí | — | Fecha efectiva de liberación a producción. |
| `semaforo` | `VARCHAR(20)` | No | `CHECK (semaforo IN ('Verde', 'Amarillo', 'Rojo'))` | Indicador sintético de salud. |

### 3.6. Tabla: `business_case`
Justificación de valor cualitativa y cuantitativa esperada ($1:1$ con `proyecto`).

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_business_case` | `BIGINT` | No | `PK` | Identificador del Business Case. |
| `id_proyecto` | `BIGINT` | No | `FK -> proyecto(id_proyecto)`, `UNIQUE` | Proyecto evaluado. |
| `ahorro_estimado` | `NUMERIC(15,2)` | No | `DEFAULT 0.00` | Reducción directa de costos. |
| `costo_evitado_estimado` | `NUMERIC(15,2)` | No | `DEFAULT 0.00` | Gastos futuros prevenidos. |
| `capacidad_liberada_horas` | `NUMERIC(10,2)` | No | `DEFAULT 0.00` | Eficiencia operativa en horas. |
| `incremento_ingreso_estimado` | `NUMERIC(15,2)` | No | `DEFAULT 0.00` | Nuevas ventas o facturación. |
| `beneficios_cualitativos` | `TEXT` | Sí | — | Impacto en imagen, servicio o clima. |
| `riesgos_cumplimiento` | `TEXT` | Sí | — | Factores regulatorios asociados. |

### 3.7. Tabla: `evaluacion_financiera`
Estructura financiera auditable y fórmulas de retorno ($1:1$ con `proyecto`).

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_evaluacion` | `BIGINT` | No | `PK` | Identificador de la evaluación. |
| `id_proyecto` | `BIGINT` | No | `FK -> proyecto(id_proyecto)`, `UNIQUE` | Proyecto financiado. |
| `costo_desarrollo` | `NUMERIC(15,2)` | No | `DEFAULT 0.00` | Costo de construcción de software. |
| `costo_implementacion` | `NUMERIC(15,2)` | No | `DEFAULT 0.00` | Despliegue y configuración. |
| `costo_consultoria` | `NUMERIC(15,2)` | No | `DEFAULT 0.00` | Servicios profesionales externos. |
| `costo_licencias` | `NUMERIC(15,2)` | No | `DEFAULT 0.00` | Software de terceros o SaaS. |
| `costo_infraestructura` | `NUMERIC(15,2)` | No | `DEFAULT 0.00` | Servidores, nube y conectividad. |
| `costo_horas_internas` | `NUMERIC(15,2)` | No | `DEFAULT 0.00` | Valor del tiempo del personal DTI. |
| `costo_mantenimiento` | `NUMERIC(15,2)` | No | `DEFAULT 0.00` | Operación anual recurrente. |
| `inversion_total` | `NUMERIC(15,2)` | No | `CHECK (inversion_total >= 0)` | Suma integral de costos de inversión. |
| `beneficio_bruto` | `NUMERIC(15,2)` | No | — | Beneficio financiero bruto proyectado. |
| `beneficio_neto` | `NUMERIC(15,2)` | No | — | `beneficio_bruto - inversion_total`. |
| `roi` | `NUMERIC(8,4)` | No | — | Retorno de inversión (`beneficio_neto / inversion_total`). |
| `payback_meses` | `NUMERIC(6,2)` | No | — | Tiempo de recuperación de la inversión. |
| `relacion_costo_beneficio` | `NUMERIC(8,4)` | No | — | Ratio `beneficio_bruto / inversion_total`. |

### 3.8. Tabla: `realizacion_valor`
Seguimiento periódico post-implementación.

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_valor` | `BIGINT` | No | `PK` | Identificador del registro de valor. |
| `id_proyecto` | `BIGINT` | No | `FK -> proyecto(id_proyecto)` | Proyecto monitoreado. |
| `impacto_estimado` | `NUMERIC(15,2)` | No | — | Valor planeado en Business Case. |
| `impacto_comprometido` | `NUMERIC(15,2)` | No | — | Valor pactado al cierre de diseño. |
| `impacto_aprobado` | `NUMERIC(15,2)` | No | — | Valor validado por finanzas. |
| `impacto_realizado` | `NUMERIC(15,2)` | No | — | Beneficio efectivamente capturado. |
| `fecha_validacion` | `DATE` | No | — | Fecha de corte del análisis de valor. |
| `observaciones` | `TEXT` | Sí | — | Justificación de desviaciones. |

### 3.9. Tabla: `etapa_proyecto`
Fases metodológicas de un proyecto.

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_etapa` | `BIGINT` | No | `PK` | Identificador de la etapa. |
| `id_proyecto` | `BIGINT` | No | `FK -> proyecto(id_proyecto)` | Proyecto padre. |
| `nombre_etapa` | `VARCHAR(100)` | No | `CHECK (nombre_etapa IN ('Análisis y Viabilidad', 'Diseño y Planificación', 'Construcción y Ejecución', 'Pruebas y Validación', 'Despliegue y Cierre'))` | Macro-etapa; todo proyecto tiene las cinco. |
| `orden_secuencia` | `INTEGER` | No | `CHECK (orden_secuencia > 0)` | Posición correlativa de la etapa. |
| `horas_estimadas` | `NUMERIC(8,2)` | No | `CHECK (horas_estimadas >= 0)` | Esfuerzo planificado en horas. |
| `horas_efectivas_reales` | `NUMERIC(8,2)` | No | `DEFAULT 0.00` | Esfuerzo consumido acumulado. |
| `fecha_inicio_est` | `DATE` | Sí | — | Fecha programada de inicio. |
| `fecha_fin_est` | `DATE` | Sí | — | Fecha programada de conclusión. |
| `estado_etapa` | `VARCHAR(50)` | No | `CHECK (estado_etapa IN ('Sin Iniciar', 'Activo', 'En Revisión', 'Pausado', 'Bloqueado', 'Cancelado', 'Completado'))` | Sincronizado con el ciclo del proyecto. |

### 3.10. Tabla: `hito_entregable`
Entregables verificables del proyecto.

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_hito` | `BIGINT` | No | `PK` | Identificador del hito. |
| `id_proyecto` | `BIGINT` | No | `FK -> proyecto(id_proyecto)` | Proyecto al que pertenece. |
| `id_etapa` | `BIGINT` | No | `FK -> etapa_proyecto(id_etapa)` | Etapa a la que está vinculado. |
| `nombre_entregable` | `VARCHAR(200)` | No | — | Descripción del producto o artefacto. |
| `fecha_comprometida` | `DATE` | No | — | Fecha pactada de entrega. |
| `fecha_entrega_real` | `DATE` | Sí | — | Fecha efectiva de liberación. |
| `estado_hito` | `VARCHAR(50)` | No | `CHECK (estado_hito IN ('Pendiente', 'Entregado', 'Aprobado', 'Atrasado'))` | Estatus de cumplimiento. |

### 3.11. Tabla: `bloqueo_interrupcion`
Registro de paro de actividades e impacto operativo.

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_bloqueo` | `BIGINT` | No | `PK` | Identificador de la interrupción. |
| `id_proyecto` | `BIGINT` | No | `FK -> proyecto(id_proyecto)` | Proyecto afectado. |
| `id_etapa` | `BIGINT` | No | `FK -> etapa_proyecto(id_etapa)` | Etapa donde ocurrió el bloqueo. |
| `causa_raiz` | `VARCHAR(100)` | No | `CHECK (causa_raiz IN ('Cambio de Prioridad', 'Dependencia Externa', 'Falta de Información', 'Recurso Reasignado', 'Incidente Operativo', 'Cambio de Alcance', 'Retrabajo', 'Espera del Cliente', 'Decisión Pendiente'))` | Categoría técnica de la causa. |
| `responsable_origen` | `VARCHAR(50)` | No | `CHECK (responsable_origen IN ('DTI', 'Cliente', 'Tercero'))` | Ente responsable del paro. |
| `fecha_inicio_bloqueo` | `TIMESTAMPTZ` | No | `DEFAULT CURRENT_TIMESTAMP` | Inicio del evento. |
| `fecha_fin_bloqueo` | `TIMESTAMPTZ` | Sí | — | Liberación del bloqueo. |
| `dias_impacto` | `NUMERIC(6,2)` | Sí | — | Días efectivos de desfase. |

### 3.12. Tabla: `registro_retrabajo`
Auditoría de devoluciones entre etapas para medición de calidad (*First Time Right*).

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_retrabajo` | `BIGINT` | No | `PK` | Identificador del evento de retrabajo. |
| `id_proyecto` | `BIGINT` | No | `FK -> proyecto(id_proyecto)` | Proyecto impactado. |
| `etapa_origen_id` | `BIGINT` | No | `FK -> etapa_proyecto(id_etapa)` | Etapa que detecta el fallo (ej. Testing). |
| `etapa_destino_id` | `BIGINT` | No | `FK -> etapa_proyecto(id_etapa)` | Etapa a la que reingresa el código (ej. Análisis). |
| `motivo_regreso` | `TEXT` | No | — | Explicación del defecto o vacante. |
| `causa_raiz_requerimiento` | `TEXT` | No | — | Diagnóstico del error inicial. |
| `horas_adicionales` | `NUMERIC(8,2)` | No | `CHECK (horas_adicionales >= 0)` | Tiempo extra invertido. |
| `impacto_dias_fecha` | `INTEGER` | No | `DEFAULT 0` | Desplazamiento del cronograma en días. |

### 3.13. Tabla: `actualizacion_avance`
Bitácora de seguimiento ágil (actualización de 60 segundos por IA).

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_actualizacion` | `BIGINT` | No | `PK` | Identificador de la actualización. |
| `id_proyecto` | `BIGINT` | No | `FK -> proyecto(id_proyecto)` | Proyecto reportado. |
| `id_usuario_registra` | `BIGINT` | No | `FK -> usuario(id_usuario)` | Usuario que rinde la bitácora. |
| `fecha_registro` | `TIMESTAMPTZ` | No | `DEFAULT CURRENT_TIMESTAMP` | Marca de tiempo del registro. |
| `porcentaje_avance` | `NUMERIC(5,2)` | No | `CHECK (porcentaje_avance BETWEEN 0 AND 100)` | Avance físico acumulado. |
| `resumen_avance` | `TEXT` | No | — | Descripción concisa de logros. |
| `proximo_hito` | `VARCHAR(200)` | Sí | — | Siguiente actividad crítica. |
| `riesgo_detectado` | `TEXT` | Sí | — | Alertas preventivas. |

### 3.14. Tabla: `compromiso_cliente`
Control explícito de dependencias del cliente interno.

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_compromiso` | `BIGINT` | No | `PK` | Identificador del compromiso. |
| `id_proyecto` | `BIGINT` | No | `FK -> proyecto(id_proyecto)` | Proyecto dependiente. |
| `id_area_cliente` | `BIGINT` | No | `FK -> area(id_area)` | Área del cliente obligada. |
| `descripcion_actividad` | `TEXT` | No | — | Tarea o validación esperada. |
| `fecha_limite_compromiso` | `DATE` | No | — | Fecha tope pactada. |
| `fecha_cumplimiento_real` | `DATE` | Sí | — | Fecha efectiva de liberación. |
| `estado_compromiso` | `VARCHAR(50)` | No | `CHECK (estado_compromiso IN ('Pendiente', 'Cumplido', 'Vencido', 'Cancelado'))` | Estatus del compromiso. |

### 3.15. Tabla Associativa: `asignacion_recurso`
Resuelve la relación Muchos-a-Muchos ($M:N$) entre `usuario` y `etapa_proyecto`.

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_asignacion` | `BIGINT` | No | `PK` | Identificador de la asignación. |
| `id_usuario` | `BIGINT` | No | `FK -> usuario(id_usuario)` | Recurso técnico asignado. |
| `id_etapa` | `BIGINT` | No | `FK -> etapa_proyecto(id_etapa)` | Etapa de trabajo asignada. |
| `id_proyecto` | `BIGINT` | No | `FK -> proyecto(id_proyecto)` | Proyecto contextual. |
| `perfil_requerido` | `VARCHAR(100)` | No | — | Rol desempeñado en la etapa. |
| `horas_asignadas` | `NUMERIC(8,2)` | No | `CHECK (horas_asignadas > 0)` | Esfuerzo asignado en horas. |
| `porcentaje_utilizacion` | `NUMERIC(5,2)` | No | `CHECK (porcentaje_utilizacion BETWEEN 0 AND 100)` | Carga de trabajo en la ventana de tiempo. |

### 3.16. Tabla Asociativa: `proyecto_empresa_impactada`
Resuelve la relación Muchos-a-Muchos ($M:N$) entre `proyecto` y `empresa`.

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_proyecto` | `BIGINT` | No | `PK, FK -> proyecto(id_proyecto)` | Proyecto que genera impacto. |
| `id_empresa` | `BIGINT` | No | `PK, FK -> empresa(id_empresa)` | Empresa receptora del impacto. |
| `id_area` | `BIGINT` | Sí | `FK -> area(id_area)` | Área impactada de esa empresa (obligatoria por API; nula en registros anteriores). |
| `nivel_impacto` | `VARCHAR(20)` | No | `CHECK (nivel_impacto IN ('Alto', 'Medio', 'Bajo'))` | Severidad o relevancia estratégica. |
| `notas_impacto` | `TEXT` | Sí | — | Detalle cualitativo del beneficio. |

### 3.17. Tabla Asociativa: `proyecto_dependencia`
Resuelve la relación Muchos-a-Muchos ($M:N$) autorreferenciada entre `proyecto` y `proyecto`.

| Campo | Tipo de Dato | Nulo | Clave / Restricción | Descripción |
| :--- | :--- | :---: | :--- | :--- |
| `id_proyecto_origen` | `BIGINT` | No | `PK, FK -> proyecto(id_proyecto)` | Proyecto predecesor / bloqueante. |
| `id_proyecto_dependiente` | `BIGINT` | No | `PK, FK -> proyecto(id_proyecto)` | Proyecto sucesor / condicionado. |
| `tipo_dependencia` | `VARCHAR(50)` | No | `CHECK (tipo_dependencia IN ('Bloqueante', 'Secuencial', 'Informativa'))` | Naturaleza del acoplamiento. |
| `descripcion_dependencia` | `TEXT` | Sí | — | Explicación técnica de la regla. |

---

## 4. Mapeo de Relaciones, Cardinalidades e Integridad Referencial

El modelo lógico aplica las reglas de conectividad, cardinalidad e integridad referencial dictadas por la teoría relacional de Adrienne Watt.

### 4.1. Matriz de Relaciones e Integridad

| Entidad Origen | Entidad Destino | Conectividad | Clave Foránea (FK) | Opcionalidad / Participación | Regla ON DELETE | Regla ON UPDATE |
| :--- | :--- | :---: | :--- | :--- | :--- | :--- |
| `empresa` | `area` | $1:M$ | `area.id_empresa` | Obligatoria en `area` | `RESTRICT` | `CASCADE` |
| `area` | `usuario` | $1:M$ | `usuario.id_area` | Obligatoria en `usuario` | `RESTRICT` | `CASCADE` |
| `usuario` | `solicitud_demanda` | $1:M$ | `solicitud_demanda.id_usuario_solicitante` | Obligatoria en `solicitud` | `RESTRICT` | `CASCADE` |
| `solicitud_demanda` | `proyecto` | $1:1$ | `proyecto.id_solicitud` | Opcional en `proyecto` | `SET NULL` | `CASCADE` |
| `usuario` | `proyecto` (Líder) | $1:M$ | `proyecto.lider_id` | Obligatoria en `proyecto` | `RESTRICT` | `CASCADE` |
| `proyecto` | `business_case` | $1:1$ | `business_case.id_proyecto` | Obligatoria en `business_case` | `CASCADE` | `CASCADE` |
| `proyecto` | `evaluacion_financiera`| $1:1$ | `evaluacion_financiera.id_proyecto` | Obligatoria en `evaluacion` | `CASCADE` | `CASCADE` |
| `proyecto` | `etapa_proyecto` | $1:M$ | `etapa_proyecto.id_proyecto` | Obligatoria en `etapa` | `CASCADE` | `CASCADE` |
| `etapa_proyecto` | `hito_entregable` | $1:M$ | `hito_entregable.id_etapa` | Obligatoria en `hito` | `CASCADE` | `CASCADE` |
| `etapa_proyecto` | `bloqueo_interrupcion`| $1:M$ | `bloqueo_interrupcion.id_etapa` | Obligatoria en `bloqueo` | `CASCADE` | `CASCADE` |
| `etapa_proyecto` | `registro_retrabajo` (Origen)| $1:M$ | `registro_retrabajo.etapa_origen_id` | Obligatoria en `retrabajo` | `RESTRICT` | `CASCADE` |
| `etapa_proyecto` | `registro_retrabajo` (Destino)| $1:M$ | `registro_retrabajo.etapa_destino_id` | Obligatoria en `retrabajo` | `RESTRICT` | `CASCADE` |
| `proyecto` | `actualizacion_avance`| $1:M$ | `actualizacion_avance.id_proyecto` | Obligatoria en `actualizacion` | `CASCADE` | `CASCADE` |
| `proyecto` | `compromiso_cliente` | $1:M$ | `compromiso_cliente.id_proyecto` | Obligatoria en `compromiso` | `CASCADE` | `CASCADE` |
| `proyecto` | `realizacion_valor` | $1:M$ | `realizacion_valor.id_proyecto` | Obligatoria en `valor` | `CASCADE` | `CASCADE` |

### 4.2. Definición de Restricciones de Integridad
1.  **Integridad de Entidad (*Entity Integrity*)**: Ninguna clave primaria (`PK`) admite valores nulos (`NOT NULL`). Todas las entidades garantizan unívocamente la identificación de cada fila.
2.  **Integridad Referencial (*Referential Integrity*)**: Toda clave foránea (`FK`) debe corresponder con un valor de clave primaria existente en la tabla padre o ser nula en caso de relaciones opcionales (ej. `proyecto.id_solicitud`).
3.  **Integridad de Dominio (*Domain Integrity*)**: Restricciones de tipo de dato y cláusulas `CHECK` que aseguran que los valores pertenezcan a rangos válidos (ej. `porcentaje_avance BETWEEN 0 AND 100`, valores permitidos de enums para estados y causas raíz).

---

## 5. Proceso de Normalización y Dependencias Funcionales

La normalización del esquema garantiza la ausencia de redundancias y la prevención de anomalías de modificación de datos.

### 5.1. Notación Formal de Dependencias Funcionales ($X \rightarrow Y$)
Para un esquema de relación $R$, el conjunto de atributos $Y$ depende funcionalmente del conjunto $X$ si cada valor de $X$ determina unívocamente el valor de $Y$.

*   `id_empresa` $\rightarrow$ `nombre_empresa`, `division`, `grupo`, `activo`
*   `id_area` $\rightarrow$ `nombre_area`, `codigo_area`, `id_empresa`
*   `id_usuario` $\rightarrow$ `nombre`, `correo`, `id_puesto`, `departamento`, `skills`, `capacidad_horas_semanales`, `activo`
*   `id_proyecto` $\rightarrow$ `nombre_proyecto`, `problema_oportunidad`, `objetivo`, `alcance`, `fuera_de_alcance`, `estado_proyecto`, `lider_id`, `semaforo`
*   `id_evaluacion` $\rightarrow$ `id_proyecto`, `costo_desarrollo`, `costo_implementacion`, `inversion_total`, `beneficio_neto`, `roi`
*   (`id_proyecto`, `id_empresa`) $\rightarrow$ `id_area`, `nivel_impacto`, `notas_impacto`
*   (`id_usuario`, `id_etapa`) $\rightarrow$ `perfil_requerido`, `horas_asignadas`, `porcentaje_utilizacion`

### 5.2. Evaluación de Formas Normales (1NF a 3NF / BCNF)

#### Primera Forma Normal (1NF)
Una relación está en 1NF si todos los atributos contienen únicamente valores atómicos indivisibles y no existen grupos repetitivos.

*   *Cumplimiento*: Se eliminaron atributos multivaluados (ej. múltiples empresas impactadas o múltiples recursos asignados a una fase) extrayéndolos a las tablas asociativas `proyecto_empresa_impactada` y `asignacion_recurso`.
*   *Atomicidad*: Campos como `alcance`, `costos` y `fechas` contienen valores escalares únicos sin listas incrustadas.

#### Segunda Forma Normal (2NF)
Una relación está en 2NF si está en 1NF y todo atributo no clave depende funcionalmente de la totalidad de la clave primaria (sin dependencias parciales).

*   *Cumplimiento*: En tablas con claves primarias compuestas (`proyecto_empresa_impactada` y `proyecto_dependencia`), los atributos no clave (`nivel_impacto`, `tipo_dependencia`) dependen de la combinación completa de las claves foráneas que forman la PK, no de una de sus partes. En tablas con PK simple, la 2NF se satisface por definición.

#### Tercera Forma Normal (3NF)
Una relación está en 3NF si está en 2NF y no existen dependencias transitivas entre atributos no clave ($X \rightarrow Y$ y $Y \rightarrow Z$).

*   *Cumplimiento*: Ningún atributo no clave depende de otro atributo no clave. Por ejemplo, en la entidad `usuario`, no se almacena el `nombre_empresa` o la `division` del usuario, sino únicamente `id_area`. La determinación de la empresa y división del usuario se resuelve transitivamente en la lectura a través del grafo de claves foráneas: `usuario` $\rightarrow$ `area` $\rightarrow$ `empresa`.

#### Forma Normal de Boyce-Codd (BCNF)
Una relación está en BCNF si para toda dependencia funcional no trivial $X \rightarrow Y$, el determinante $X$ es una clave candidata superclave.

*   *Cumplimiento*: Todas las tablas definidas poseen determinantes que constituyen claves candidatas o primarias unívocas (`id_proyecto`, `id_usuario`, `id_evaluacion`).

### 5.3. Eliminación de Anomalías de Datos
La adhesión estricta a 3NF/BCNF elimina las tres anomalías clásicas descriptas por Watt:

1.  **Anomalía de Inserción**: Se puede crear un nuevo usuario o registrar una nueva empresa en el sistema sin necesidad de asociarlos de forma ficticia a un proyecto existente.
2.  **Anomalía de Actualización**: Si una empresa cambia de nombre o división, la modificación se ejecuta en una sola tupla de la tabla `empresa`, reflejándose automáticamente en todos los proyectos vinculados sin riesgo de inconsistencias.
3.  **Anomalía de Eliminación**: La cancelación o borrado de un proyecto no ocasiona la pérdida accidental de la información histórica del cliente, de las áreas o del catálogo de recursos de DTI.

---

## 6. Rendimiento, Mantenibilidad y Estrategia OLTP/OLAP

Para cumplir con las metas de escalabilidad y tolerancia a fallos enunciadas por Kleppmann, el diseño incorpora optimizaciones de rendimiento y separación de capas de lectura y escritura.

*   **Procesamiento Operativo Transaccional**: Las solicitudes interactivas de escritura de alta frecuencia (registro de avances, inserción de bloqueos) se dirigen exclusivamente a la base de datos PostgreSQL/OLTP en 3NF.
*   **Replicación y Transmisión de Log de Eventos (CDC)**: Un proceso de captura de transacciones (*Change Data Capture*) transmite el registro de cambios (*Write-Ahead Log / WAL*) hacia el Data Warehouse.
*   **Capa de Inteligencia y Análisis Masivo (OLAP)**: Los informes ejecutivos de portafolio, las simulaciones de escenarios y el Scorecard multidimensional se sirven desde vistas materializadas e índices de almacenamiento columnar en el almacén de datos.

### 6.1. Estrategia de Indización B-Tree
Se definen índices B-Tree en la capa física para acelerar las operaciones de combinación (*joins*) y filtros en las consultas OLTP más frecuentes:

*   **Claves Foráneas**: Índices B-Tree en todas las columnas `FK` (`id_proyecto`, `id_area`, `lider_id`, `id_etapa`) para eliminar bloqueos de tabla (*table scans*) durante la navegación referencial.
*   **Filtros Frecuentes de Negocio**: Índices en `proyecto.estado_proyecto`, `proyecto.semaforo`, `solicitud_demanda.estado_demanda` y `bloqueo_interrupcion.causa_raiz`.
*   **Marcas de Tiempo**: Índices ordenados en `actualizacion_avance.fecha_registro` y `bloqueo_interrupcion.fecha_inicio_bloqueo` para facilitar la recuperación de bitácoras recientes.

### 6.2. Vistas Materializadas para Consultas Analíticas Intensivas
Para evitar degradar el rendimiento de la base de datos OLTP con consultas agregadas complejas (por ejemplo, el cálculo del Scorecard de Transformación o la utilización de capacidad por perfil), se implementan **Vistas Materializadas** que se refrescan de manera asíncrona:

*   `vw_resumen_capacidad_perfil`: Agrega las horas asignadas en `asignacion_recurso` frente a la capacidad de `usuario` para calcular el porcentaje de saturación por perfil técnico (Backend, Frontend, QA).
*   `vw_scorecard_productividad`: Consolida métricas de *Lead Time*, *Cycle Time*, porcentaje de *First Time Right* (a partir de `registro_retrabajo`) y desviaciones contra la fecha comprometida.

### 6.3. Sincronización OLTP a OLAP mediante Change Data Capture (CDC)
Las consultas ad-hoc e informes de Inteligencia de Negocios para Dirección (ej. análisis de correlaciones cualitativas o simulación de escenarios de portafolio) se ejecutan fuera del motor OLTP. 

Un proceso de **Captura de Datos Cambiados (CDC)** lee el registro de transacciones (*Write-Ahead Log / WAL*) del motor relacional y replica los eventos en tiempo real hacia un Data Warehouse (organizado en un Esquema en Estrella con tablas de hechos de eventos de proyectos y dimensiones de tiempo, empresa y recurso). Esto garantiza el aislamiento total entre las operaciones de alta concurrencia y el análisis cuantitativo masivo.
