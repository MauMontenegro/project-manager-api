# Referencia del Backend y la API — Petroil Project Manager

Documento de referencia para el desarrollo del frontend. Describe convenciones, enums, modelos de datos, reglas de negocio y todos los endpoints disponibles.

- **Base URL (local):** `http://localhost:8000`
- **Prefijo de la API:** `/api/v1`
- **Documentación interactiva (OpenAPI):** `/docs` (Swagger) y `/openapi.json` (útil para generar clientes tipados)
- **Health check:** `GET /health` → `{"status": "ok"}`
- **Formato:** JSON (`Content-Type: application/json`)
- **Autenticación:** `Authorization: Bearer <token>` en todo `/api/v1` (salvo `POST /auth/login`): la sesión que emite `POST /auth/login` (correo y contraseña) o un ID token de Firebase (Google o Microsoft). Con `AUTH_ENABLED=false` (desarrollo) no se pide token y cada petición actúa como un Administrador local; con `LOCAL_ID_USUARIO=<id>` ese Administrador local es esa persona del Equipo (para probar perfil, tareas propias y menciones). Ver §2.5.
- **CORS:** permitido para `http://localhost:3000` y `http://localhost:5173` (configurable con `CORS_ORIGINS`).

---

## 1. Stack

| Capa | Tecnología |
| :--- | :--- |
| Lenguaje / framework | Python 3.12, FastAPI (asíncrono) |
| ORM | SQLAlchemy 2.0 (`AsyncSession`) + `asyncpg` |
| Base de datos | PostgreSQL 16 |
| Validación | Pydantic v2 |
| Migraciones | Alembic |

Arquitectura en capas: `api/v1/endpoints` (HTTP) → `services` (reglas de negocio) → `models` (SQLAlchemy). El esquema relacional tiene 17 tablas en 3FN; ver `arquitectura-base-datos-petroil.md`.

---

## 2. Convenciones de la API

### 2.1 Tipos de datos en JSON

| Tipo | Representación | Ejemplo |
| :--- | :--- | :--- |
| Identificadores | entero | `12` |
| **Decimales** (horas, porcentajes, dinero, `dias_impacto`) | **string** | `"80.00"` |
| Fechas (`date`) | `YYYY-MM-DD` | `"2026-10-06"` |
| Fecha-hora (`datetime`) | ISO 8601 en UTC | `"2026-10-06T18:12:19Z"` |
| Enums | string exacto, **con tildes y mayúsculas** | `"En Revisión"` |

> **Importante:** los decimales llegan como string. Al **enviarlos** se aceptan tanto número como string (`80` o `"80.00"`). En el frontend conviértalos con `Number()`/una librería decimal solo para mostrar o calcular.
>
> Los `datetime` que se **envían** deben incluir zona horaria (`Z` o `+00:00`); si no, el backend responde 422.

### 2.2 PATCH parcial

Los `PATCH` aceptan solo los campos a modificar. Enviar un campo no nulable con `null` produce un error 422 (ver §2.4).

### 2.3 Paginación

Solo el portafolio (`GET /proyectos`) devuelve un envoltorio con total. El resto de listados devuelven un **arreglo simple** y aceptan `limit` (1–200, default 50) y `offset` (≥ 0) cuando se indica.

```json
{ "items": [ ... ], "total": 134, "limit": 50, "offset": 0 }
```

### 2.4 Errores

| Código | Cuándo | Forma del `detail` |
| :--- | :--- | :--- |
| `404` | El recurso referenciado no existe (incluye FKs en el cuerpo) | `string` |
| `409` | Conflicto: duplicados (correo, empresa, código de área, asignación, orden de etapa, solicitud ya usada) o violación de integridad en BD | `string` |
| `422` (regla de negocio) | Cambio de ciclo inválido (etapa, estatus o avance), usuario inactivo, proyecto cerrado, bloqueo ya cerrado, fechas incoherentes, campo nulo no permitido | `string` |
| `422` (validación de esquema) | Tipo, rango o enum inválido en el cuerpo/query | `array` de objetos `{loc, msg, type}` (formato estándar de FastAPI) |

El frontend debe distinguir ambos 422 comprobando si `detail` es `string` o `array`.

```json
{ "detail": "El estatus 'Pausado' no está permitido en 'Análisis y Viabilidad'. Permitidos: Sin Iniciar, Activo, En Revisión, Cancelado" }
```

---

### 2.5 Autenticación y permisos

**Correo y contraseña.** `POST /auth/login` `{correo, password}` → `{access_token, token_type: "bearer", expira, password_temporal}`. La sesión es un JWT HS256 firmado con `SECRET_KEY` (obligatoria con `AUTH_ENABLED=true`, ≥ 32 caracteres) que dura `SESION_HORAS` (12 por defecto). Lleva la versión de la contraseña: al cambiarla o restablecerla, las sesiones anteriores dan `401`; también si la persona se desactiva. Contraseñas con hash scrypt; nunca salen de la API (`UsuarioRead.tiene_password` indica si ya tiene una). Reglas: 8–128 caracteres, letras y números, distinta del correo y del nombre. Tras 5 intentos fallidos con un correo en 15 minutos → `429`. El mensaje de error no distingue si el correo existe.

- **Contraseña temporal** (`password_temporal` en `/sesion`): la asigna otra persona; mientras no se cambie, solo se permiten `GET /sesion` y `POST /auth/password` (lo demás → `403`).
- `POST /auth/password` `{actual, nueva}` → nueva sesión (`SesionToken`); cierra las demás. Registra en la bitácora.
- `POST /usuarios/{id}/password` `{nueva?}` → `{password_temporal}` (sin `nueva`, la genera: 12 caracteres). Administrador: a cualquiera; Gerente: a su departamento salvo Administradores y Gerentes; nunca a uno mismo. Solo personas activas con correo. Registra en la bitácora.
- Arranque (o si nadie puede entrar): `docker compose exec api python -m app.cli.password <correo>` imprime una temporal.

**Firebase (opcional).** La API valida el ID token de Firebase (firma, emisor, audiencia `FIREBASE_PROJECT_ID`, vigencia) y busca al usuario **activo** cuyo `correo` coincide con el del token. Los correos de `BOOTSTRAP_ADMIN_EMAILS` entran como Administrador aunque aún no estén en el Equipo (sirve para dar de alta al primer Administrador). Con `AUTH_ENABLED=false`, la sesión actúa como la persona `LOCAL_ID_USUARIO` **con su rol** (cambiándolo se prueba cada perfil); sin ella, como un Administrador local.

**Visibilidad (qué se puede consultar).** Además de lo que cada rol puede modificar, la lectura de proyectos se acota por rol (`app/services/visibilidad.py`):

- Administrador: todos.
- Gerente y Líder: los de su departamento (el Gerente, también los que aún no tienen departamento).
- Cualquiera: los que lidera, en los que está asignado o tiene alguna tarea.
- Un proyecto conjunto se ve entero: quien ve una parte (el conjunto o un subproyecto) ve el conjunto y todos sus subproyectos.

Aplica a `GET /proyectos` (portafolio), `/proyectos/{id}` y sus etapas, asignaciones, involucrados y tareas; `/tareas/{id}`, su actividad, involucrados, reprogramaciones y comentarios; `/bloqueos`, `/bloqueos/resumen` y `/bloqueos/{id}`; `/usuarios/{id}/asignaciones`, y `GET /tareas?id_usuario=` de otra persona (sus recurrentes y las de proyectos visibles). Lo que no se puede ver responde **`404`**, como si no existiera. Sin cambios: el directorio de personas, la capacidad y los conteos de los equipos de trabajo.

| Rol | Puede |
| :--- | :--- |
| `Administrador` | Todo: cualquier departamento, otorgar cualquier rol, configuración, catálogos, eliminar proyectos y empresas, ver costos y bitácora global. |
| `Gerente` | Gestionar personas y ausencias de **su** departamento (y darles rol `Usuario` o `Líder`), sus proyectos, etapas y etiquetas; crear proyectos en su departamento y conjuntos; catálogos, costos y bitácora global. |
| `Líder` | Crear proyectos en **su** departamento y gestionar los que lidera (editar, ciclo, tareas, asignaciones). No crea conjuntos ni gestiona personas o configuración. No ve `costo_hora`. |
| `Usuario` | Consultar; trabajar **sus** tareas (moverlas, horas reales, comentarios), sus tareas recurrentes y ausencias; gestionar proyectos solo si lidera alguno. No ve `costo_hora` (viene `null`). |

Errores: `401` sin token, token inválido o expirado; `403` cuenta no registrada en el Equipo o acción fuera de su alcance.

---

## 3. Enumeraciones

Los valores se envían y reciben **tal cual** se muestran aquí.

| Enum | Valores |
| :--- | :--- |
| `Departamento` | `Dirección`, `Infraestructura`, `Procesos`, `Desarrollo de Software` |
| `TipoRecurso` | `Interno`, `Externo`, `Activo` |
| `RolSistema` | `Administrador`, `Gerente`, `Líder`, `Usuario` |
| `NivelSkill` | `Básico`, `Intermedio`, `Experto` |
| `TipoAusencia` | `Vacaciones`, `Permiso`, `Incapacidad`, `Capacitación`, `Otro` |
| `EstadoProyecto` | `Sin Iniciar`, `Activo`, `En Revisión`, `Pausado`, `Bloqueado`, `Cancelado`, `Completado` |
| `Semaforo` | `Verde`, `Amarillo`, `Rojo` |
| `NivelImpacto` | `Alto`, `Medio`, `Bajo` |
| `NombreEtapa` | `Análisis y Viabilidad`, `Diseño y Planificación`, `Construcción y Ejecución`, `Pruebas y Validación`, `Despliegue y Cierre` |
| `EstadoEtapa` | mismos valores que `EstadoProyecto` |
| `EstadoTarea` | `Pendiente`, `En progreso`, `En revisión`, `Finalizado` |
| `CausaRaiz` (bloqueos) | `Cambio de Prioridad`, `Dependencia Externa`, `Falta de Información`, `Recurso Reasignado`, `Incidente Operativo`, `Cambio de Alcance`, `Retrabajo`, `Espera del Cliente`, `Decisión Pendiente`, `Dependencia Interna` (solo la registra el sistema) |
| `ResponsableOrigen` | `DTI`, `Cliente`, `Tercero` |

Enums del modelo de datos que **aún no tienen endpoints** (para futuras pantallas): `EstadoDemanda` (`Solicitado`, `Analizado`, `Priorizado`, `Esperando Capacidad`, `Planeado`, `En Ejecución`, `Rechazado`), `EstadoHito` (`Pendiente`, `Entregado`, `Aprobado`, `Atrasado`), `EstadoCompromiso` (`Pendiente`, `Cumplido`, `Vencido`, `Cancelado`), `TipoDependencia` (`Bloqueante`, `Secuencial`, `Informativa`).

---

## 4. Modelo de dominio (visión para el frontend)

```
Empresa 1─M Área 1─M Usuario
                       │ (líder)
Empresa/Área/Usuario ─ SolicitudDemanda 1─1 Proyecto ◄── lider_id (Usuario)
                                            │
        ┌───────────────┬───────────────────┼───────────────────┐
   Empresas impactadas  Etapas (1─M)   Bloqueos (1─M)   [aún sin API: business case, evaluación
   (M:N, con nivel)       │                 │            financiera, hitos, retrabajo, avances,
                    Asignaciones         (por etapa)     compromisos, valor, dependencias]
                    (Usuario ↔ Etapa)
```

Orden de creación obligatorio (por FKs): **Empresa → Área → Usuario → Proyecto (crea sus 5 etapas) → Asignación / Bloqueo**.

---

## 5. Reglas de negocio

1. **Ciclo de vida del proyecto.** Todos los proyectos (de las tres áreas) recorren cinco macro-etapas. El proyecto tiene una `etapa_actual`, un estatus (`estado_proyecto`) y un `porcentaje_avance` **calculado con las tareas**. Cada etapa vale 20 % del proyecto:

   | # | Etapa | Porción del avance | Estatus permitidos | Qué pasa |
   | :-: | :--- | :--- | :--- | :--- |
   | 1 | `Análisis y Viabilidad` | 0 – 20 % | `Sin Iniciar`, `Activo`, `En Revisión`, `Cancelado` | Se define el "Qué" (levantamientos, requerimientos, viabilidad) |
   | 2 | `Diseño y Planificación` | 20 – 40 % | `Activo`, `En Revisión`, `Pausado`, `Cancelado` | Se define el "Cómo" (arquitectura, cronogramas, flujos To-Be) |
   | 3 | `Construcción y Ejecución` | 40 – 60 % | `Activo`, `Bloqueado`, `Pausado`, `Cancelado` | Se construye (programar, instalar hardware, redactar manuales) |
   | 4 | `Pruebas y Validación` | 60 – 80 % | `Activo`, `En Revisión`, `Bloqueado`, `Cancelado` | Se valida (QA, UAT, pruebas de estrés, simulaciones) |
   | 5 | `Despliegue y Cierre` | 80 – 100 % | `Activo`, `Completado` | Se lanza y finaliza (Go-Live, encendido, capacitación, cierre) |

   - Un proyecto nace en `Análisis y Viabilidad` · `Sin Iniciar` · 0 %, con sus cinco etapas creadas.
   - Se avanza solo a la **siguiente** etapa; se puede **regresar** a cualquier anterior (retrabajo).
   - El estatus debe estar entre los permitidos por la etapa. Al cambiar de etapa sin indicar estatus se usa `Activo`.
   - **Avance**: cada etapa aporta 20 % × tareas `Finalizado` / tareas de la etapa. Una etapa sin tareas aporta su 20 % si ya se pasó y 0 % si es la actual o posterior. Un proyecto `Completado` está al 100 %. El avance no se envía nunca.
   - **Avance automático**: al finalizar la última tarea pendiente de la etapa actual, el proyecto pasa solo a la siguiente etapa como `Activo` (en la etapa 5 queda `Completado`). Un proyecto `Sin Iniciar` pasa a `Activo` en cuanto una de sus tareas sale de `Pendiente`. Los cambios manuales de ciclo no disparan este avance (así se puede regresar a una etapa ya terminada).
   - `Completado` fija `fecha_real_cierre` (la enviada o, por defecto, hoy). `Completado` y `Cancelado` son definitivos: tampoco admiten cambios en sus tareas.
   - Las etapas anteriores a la actual quedan `Completado`; la actual toma el estatus del proyecto; las posteriores, `Sin Iniciar`.

   Etapa y estatus **no** se editan con `PATCH /proyectos/{id}`; solo con `PATCH /proyectos/{id}/estado` (o solos, por las tareas).
2. **Líder activo.** `lider_id` debe ser un usuario existente y `activo = true`.
3. **Solicitud única.** Una solicitud de demanda solo puede originar un proyecto; al crearlo, la solicitud pasa a `En Ejecución`.
4. **Empresas impactadas.** No se pueden repetir empresas en un mismo proyecto; todas deben existir.
5. **Etapas.** Son siempre las cinco macro-etapas (orden 1–5); no se crean ni se borran. Solo se planifican horas y fechas.
6. **Asignaciones.** La etapa debe pertenecer al proyecto, el usuario debe estar activo, el proyecto no puede estar `Completado` ni `Cancelado`, y un usuario no puede asignarse dos veces a la misma etapa.
7. **Semáforo calculado.** `semaforo` no se envía (si llega, se ignora): el backend lo calcula y explica en `semaforo_motivo`.
   - *Avance esperado a hoy*: cada etapa con `fecha_inicio_est` y `fecha_fin_est` cubre su 20 % (regla 1) de forma lineal entre esas fechas.
   - `Rojo`: fecha comprometida vencida sin completar, o avance real ≥ 15 puntos por debajo del esperado.
   - `Amarillo`: entre 5 y 15 puntos por debajo, o faltan ≤ 14 días para la fecha comprometida y aún no está en `Despliegue y Cierre`.
   - `Verde`: en cualquier otro caso (incluye proyectos sin fechas para evaluar).
   - `Completado`: `Verde`, o `Rojo` si cerró después de la fecha comprometida. `Cancelado`: conserva su último semáforo.
   - Se recalcula al crear, editar, cambiar el ciclo o planificar etapas, y una vez al día al consultar el portafolio o un proyecto.
8. **Bloqueos.** Se reportan sobre una tarea (o una etapa). `dias_impacto`/`horas_impacto` son tiempo **hábil** calculado por el backend (nunca se envían); un bloqueo sin `fecha_fin_bloqueo` está **abierto** y devuelve su tiempo hasta ahora. Ver §6.6.
9. **Usuarios.** El correo es único. `DELETE` es una **baja lógica** (`activo = false`): el usuario sigue apareciendo en los listados salvo que se filtre por `activo=true`.
10. **Portafolio por empresa.** `id_empresa` coincide con proyectos donde la empresa es una de las **impactadas** o la **solicitante** de la demanda de origen.

---

## 6. Endpoints

Todas las rutas van bajo `/api/v1`.

### 6.1 Catálogos organizacionales

#### `POST /empresas` → `201`
```json
{ "nombre_empresa": "Petroil Combustibles", "division": "Combustibles", "grupo": "Petroil" }
```
Respuesta `EmpresaRead`:
```json
{ "id_empresa": 1, "nombre_empresa": "Petroil Combustibles", "division": "Combustibles",
  "grupo": "Petroil", "activo": true, "fecha_creacion": "2026-10-06T18:12:19Z" }
```
Errores: `409` nombre duplicado.

#### `GET /empresas` → `200`
Arreglo de `EmpresaRead`, ordenado por nombre. Sin paginación.

#### `DELETE /empresas/{id_empresa}` → `204`
Elimina la empresa y sus áreas. Solo Administrador (`403`). `404` si no existe; `409` si está en uso: impactada en algún proyecto, con solicitudes de demanda, o con áreas usadas por solicitudes o compromisos de cliente.

#### `POST /empresas/eliminar` → `200`
Eliminación en lote. Cuerpo `{ "ids": [int] }` (1–500). Elimina las que no están en uso (con sus áreas) y reporta las demás sin fallar:
```json
{ "eliminadas": [13, 14],
  "no_eliminadas": [{ "id_empresa": 1, "nombre_empresa": "Corporativo", "motivo": "En uso: 1 proyecto la tiene como impactada" }] }
```
Solo Administrador (`403`). Cada baja queda en la bitácora (`entidad = "empresa"`).

#### `POST /areas` → `201`
```json
{ "id_empresa": 1, "nombre_area": "DTI", "codigo_area": "DTI-01" }
```
Respuesta `AreaRead`: el mismo cuerpo más `id_area`.
Errores: `404` empresa inexistente; `409` `codigo_area` duplicado.

#### `GET /areas` → `200`
Query: `id_empresa` (opcional). Arreglo de `AreaRead`, ordenado por nombre.

#### `GET /puestos` → `200`
Catálogo administrable de puestos de la DTI. Arreglo de `PuestoRead` (`{ "id_puesto": 1, "nombre_puesto": "Administrador" }`), ordenado por nombre. La migración 0002 lo siembra con: Administrador, Gerente, Coordinador, Líder Técnico, Especialista, Analista, Desarrollador, Técnico.

#### `POST /puestos` → `201`
```json
{ "nombre_puesto": "Arquitecto de Soluciones" }
```
1–100 caracteres (se recortan espacios). Errores: `409` nombre duplicado (sin distinguir mayúsculas).

#### `DELETE /puestos/{id_puesto}` → `204`
Elimina el puesto. Errores: `404` inexistente; `409` si alguna persona (activa o no) lo tiene asignado.

---

### 6.2 Equipo: recursos

Un recurso es una persona **interna**, un **externo** (proveedor/consultor) o un **activo** no humano (servidor, licencia, ambiente).

**`UsuarioRead`**
```json
{ "id_usuario": 2, "tipo_recurso": "Interno", "nombre": "Beto Dev", "correo": "beto@petroil.com",
  "id_puesto": 7, "departamento": "Desarrollo de Software", "id_jefe": 4, "rol": "Usuario",
  "skills": [{ "nombre": "Python", "nivel": "Experto" }, { "nombre": "React", "nivel": "Intermedio" }],
  "capacidad_horas_semanales": "40.00", "porcentaje_proyectos": "80.00", "costo_hora": "450.00",
  "proveedor": null, "fecha_fin_contrato": null, "activo": true }
```
`costo_hora` llega `null` a los Usuarioes. `id_puesto`/`departamento` pueden ser `null` en registros anteriores a la migración 0002.

#### `POST /usuarios` → `201`
| Campo | Tipo | Obligatorio | Reglas |
| :--- | :--- | :---: | :--- |
| `tipo_recurso` | `TipoRecurso` | no | default `Interno` |
| `nombre` | string | sí | 1–150 caracteres |
| `correo` | email | personas | único (sin distinguir mayúsculas); no aplica a activos |
| `id_puesto` | int | personas | debe existir en `/puestos` |
| `departamento` | `Departamento` | sí | Gerente: solo el suyo |
| `id_jefe` | int | no | persona existente, no activo; sin ciclos («reporta a») |
| `rol` | `RolSistema` | no | default `Usuario`; un Gerente puede dar `Líder`; `Gerente` y `Administrador` solo los otorga el Administrador |
| `skills` | `{nombre, nivel}[]` | no | máx. 30; nombres nuevos se agregan al catálogo; repetidos se ignoran |
| `capacidad_horas_semanales` | decimal | sí | 0–999 |
| `porcentaje_proyectos` | decimal | no | 0–100, default 100 (el resto es operación/soporte) |
| `costo_hora` | decimal | no | ≥ 0 |
| `proveedor`, `fecha_fin_contrato` | string, date | externos | `proveedor` obligatorio en externos; se limpian en otros tipos |
| `activo` | bool | no | default `true` |

Errores: `403` fuera de alcance; `404` puesto/jefe inexistente; `409` correo duplicado; `422` reglas por tipo o ciclo de jefatura.

#### `GET /usuarios` → `200`
Query: `id_puesto`, `departamento`, `tipo_recurso`, `id_jefe`, `skill` (sin distinguir mayúsculas) + `nivel_min`, `activo`, `q`, `limit`, `offset`.

#### `GET /usuarios/{id}` · `PATCH /usuarios/{id}` · `DELETE /usuarios/{id}`
PATCH acepta cualquier subconjunto; `null` solo en campos opcionales; `skills` reemplaza la lista. DELETE es baja lógica (no puedes darte de baja a ti mismo).

#### `GET /usuarios/{id}/asignaciones` → `200`
Asignaciones con proyecto y etapa resueltos, `horas_en_tareas` (sus tareas en esa etapa), `vigente` (etapa no completada y proyecto activo) y `costo_estimado` (`horas_en_tareas × costo_hora`, solo para quien ve costos).

#### `GET|POST /usuarios/{id}/ausencias` · `DELETE /ausencias/{id}`
`{tipo, fecha_inicio, fecha_fin, nota?}`. Las gestiona la propia persona o quien gestiona su departamento. `409` si se traslapa con otra.

#### `GET /usuarios/{id}/bitacora` → `200`
Historial de cambios que afectan a la persona (altas, ediciones con `cambios: {campo: [antes, después]}`, ausencias, asignaciones).

### 6.2.1 Catálogos, capacidad y sesión

| Endpoint | Descripción |
| :--- | :--- |
| `GET /sesion` | Usuario autenticado: `{id_usuario, nombre, correo, rol, departamento, auth_habilitada}`. |
| `GET /perfil` | `UsuarioRead` de quien inició sesión. `404` si la sesión no está ligada a una persona del Equipo. |
| `PATCH /perfil` | Cada persona edita lo suyo: `{ nombre?, skills? }` (skills reemplaza la lista). Puesto, rol, capacidad, etc. los cambia su gerente con `PATCH /usuarios/{id}`. Queda en la bitácora. |
| `GET /skills` | Catálogo `{id_skill, nombre, personas}`. |
| `PATCH /skills/{id}` | Renombrar (`{nombre}`); `409` si ya existe → fusionar. Administrador/Gerente. |
| `POST /skills/{id}/fusionar` | `{id_destino}`: mueve a las personas (conservando el nivel más alto) y elimina el origen. |
| `DELETE /skills/{id}` | Lo quita del catálogo y de todas las personas. |
| `GET /capacidad` | Ver abajo. |
| `GET /bitacora` | Últimos cambios (`entidad`, `limit`). Administrador/Gerente. |

**`GET /capacidad`** — Query: `desde` (se ajusta al lunes; default hoy), `semanas` (1–26, default 12), `id_usuario` o filtros `departamento`, `id_puesto`, `tipo_recurso`, `skill`, `nivel_min`. Devuelve por persona activa `{id_usuario, capacidad_planificable, semanas: [{inicio, horas_disponibles, horas_asignadas, utilizacion, dias_ausencia}]}`. `horas_asignadas` de cada semana son las horas de tareas que caen en ella.

Modelo: planificable = capacidad × `porcentaje_proyectos`; disponibles de la semana = planificable × días hábiles sin ausencia / 5; la carga sale solo de las tareas no finalizadas: sus horas se reparten entre los días hábiles de sus fechas. Las asignaciones no consumen capacidad. No cuentan tareas de etapas `Completado`/`Cancelado` ni proyectos `Completado`, `Cancelado` o `Pausado`. `utilizacion` es `null` si no hay horas disponibles.

---

### 6.3 Proyectos y portafolio

**`ProyectoRead`** (usado en el listado)
```json
{ "id_proyecto": 1, "nombre_proyecto": "Portal", "problema_oportunidad": "...", "objetivo": "...",
  "alcance": "...", "fuera_de_alcance": "...", "fecha_tentativa": null, "fecha_comprometida": "2026-12-15",
  "fecha_inicio": "2026-10-01", "fecha_real_cierre": null, "horas_presupuestadas": "400.00", "horas_presupuestadas_manual": false, "id_solicitud": null, "lider_id": 1,
  "etapa_actual": "Construcción y Ejecución", "estado_proyecto": "Activo", "porcentaje_avance": "42.00",
  "semaforo": "Amarillo", "semaforo_motivo": "Avance 42 % vs. 50 % esperado",
  "departamento": "Infraestructura", "es_conjunto": false, "id_proyecto_padre": null,
  "etiquetas": [ { "id_etiqueta": 3, "departamento": "Infraestructura", "nombre": "Redes", "color": "#2563eb" } ],
  "subproyectos": [] }
```

**Espacios por departamento.** Cada proyecto pertenece a `Infraestructura`, `Procesos` o `Desarrollo de Software` (`departamento`; nulo solo en proyectos antiguos sin asignar). Un **proyecto conjunto** (`es_conjunto: true`, sin departamento ni etapas) agrupa un subproyecto por departamento participante (`subproyectos`, cada uno con `id_proyecto_padre`); su avance (ponderado por las horas presupuestadas), fechas, presupuesto, estatus y semáforo (el peor) se consolidan de ellos. Puede tener **tareas generales** propias (sin etapa, no cuentan en el avance) y las tareas del conjunto y de todos sus subproyectos pueden depender entre sí (§6.7). `etapa_actual` es el nombre de una de las etapas del proyecto (nula en un conjunto).

**Permisos.** Crear un proyecto: Gerente de su departamento o Administrador; un conjunto: cualquier Gerente o el Administrador. Editar, cambiar el ciclo, planificar etapas, asignar y gestionar tareas: el líder, el Gerente de su departamento o el Administrador (un conjunto, solo su líder o el Administrador). Todos pueden consultar todo.

**`ProyectoDetalle`** = `ProyectoRead` + `padre` (`{ id_proyecto, nombre_proyecto, lider_id }` en un subproyecto) + `empresas_impactadas` + `horas_en_tareas` (suma de horas de sus tareas, para mostrar el presupuesto restante):
```json
"empresas_impactadas": [ { "id_empresa": 1, "id_area": 2, "nivel_impacto": "Alto", "notas_impacto": null } ]
```

#### `POST /proyectos` → `201` (devuelve `ProyectoDetalle`)
| Campo | Tipo | Obligatorio | Notas |
| :--- | :--- | :---: | :--- |
| `nombre_proyecto` | string | sí | 1–200 |
| `objetivo` | string | sí | no vacío |
| `problema_oportunidad`, `alcance`, `fuera_de_alcance` | string | no | `""` = sin definir (también al editar) |
| `lider_id` | int | sí | usuario activo |
| `id_solicitud` | int \| null | no | ver regla 3 |
| `fecha_inicio`, `fecha_tentativa`, `fecha_comprometida` | date \| null | no | el inicio no puede ser posterior al fin (comprometida o, si no hay, tentativa) |
| `horas_presupuestadas` | decimal \| null | no | ≥ 0; tope para la suma de horas de las tareas. **Omitido o `null`: se calcula** con el calendario laboral (§6.8) entre `fecha_inicio` y el fin; sin ambas fechas queda sin límite. Con valor: se fija a mano (`horas_presupuestadas_manual = true`) |
| `empresas_impactadas` | array | no | `[{ id_empresa, id_area, nivel_impacto, notas_impacto? }]`, sin empresas repetidas; `id_area` es obligatoria y debe pertenecer a esa empresa (`id_area` es `null` solo en proyectos anteriores) |
| `departamento` | `DepartamentoProyecto` | sí, salvo conjunto | espacio del proyecto |
| `es_conjunto` | bool | no | `true`: proyecto conjunto (sin `departamento`) |
| `subproyectos` | array | en conjunto | `[{ departamento, lider_id }]`, mínimo dos departamentos distintos. Cada subproyecto copia los textos y las fechas del conjunto |
| `etiquetas` | int[] | no | ids de etiquetas de sus departamentos (en un conjunto, cada subproyecto recibe las de su departamento) |

`etapa_actual`, `estado_proyecto` y `porcentaje_avance` no se envían: inicia `Sin Iniciar` · 0 % en la primera etapa, con una copia de la plantilla de etapas de su departamento (§6.4.1).
Errores: `404` (líder, solicitud, empresa o área inexistente); `409` solicitud ya usada; `422` líder inactivo, empresas repetidas, falta `id_area` o el área no es de esa empresa.

#### `GET /proyectos` → `200` — Portafolio
Query (todos opcionales y combinables): `departamento` (espacio: sus proyectos y los conjuntos en que participa), `semaforo`, `id_empresa`, `estado` (`EstadoProyecto`), `etapa` (nombre de la etapa actual), `lider_id`, `etiquetas` (repetible: `?etiquetas=1&etiquetas=2`, con cualquiera de ellas), `limit` (default 50, máx. 200), `offset`.
Solo devuelve proyectos de primer nivel; los conjuntos traen sus `subproyectos`. Un conjunto cumple cada filtro si lo cumple él o alguno de sus subproyectos (del departamento, si se indica).
Respuesta `{ items: ProyectoRead[], total, limit, offset }`, ordenado del más reciente al más antiguo. `total` es el conteo con los filtros aplicados (úselo para paginar).

#### `GET /proyectos/{id_proyecto}` → `200`
`ProyectoDetalle`. `404` si no existe.

#### `PATCH /proyectos/{id_proyecto}` → `200`
Campos editables: `nombre_proyecto`, `problema_oportunidad`, `objetivo`, `alcance`, `fuera_de_alcance`, `fecha_inicio`, `fecha_tentativa`, `fecha_comprometida`, `horas_presupuestadas`, `lider_id`, `empresas_impactadas`, `etiquetas` (reemplaza la lista) y `departamento` (solo proyectos normales: lo mueve de espacio conservando sus etapas y quitando las etiquetas del anterior). En un conjunto no se editan fechas ni presupuesto (`422`). `horas_presupuestadas` con valor lo fija a mano; `null` vuelve al cálculo automático, que se rehace al cambiar las fechas. Al cambiar fechas o presupuesto, las tareas existentes deben seguir cabiendo (`422` si no). Las fechas sí aceptan `null` para borrarlas; el resto no. `empresas_impactadas`, si se envía, **reemplaza la lista completa** con las mismas reglas que al crear (área obligatoria y de esa empresa, sin repetidas); `[]` las quita todas. Devuelve `ProyectoDetalle`.

#### `DELETE /proyectos/{id_proyecto}` → `204`
Borrado **definitivo** del proyecto con sus etapas, asignaciones, bloqueos, hitos, retrabajos, avances, compromisos, empresas impactadas y dependencias. Si venía de una solicitud de demanda en `En Ejecución`, esta vuelve a `Planeado`. Queda registrado en la bitácora. Permiso: solo Administrador (`403`). `404` si no existe. Para detener un proyecto conservando su historial, usar el estatus `Cancelado`. Un conjunto se elimina con sus subproyectos.

#### `POST /proyectos/{id}/subproyectos` → `201` · `DELETE /proyectos/{id}/subproyectos/{id_subproyecto}` → `200`
Suma (`{ departamento, lider_id }`) o quita un departamento de un conjunto; ambos devuelven el conjunto. Sumar: líder del conjunto, Administrador o el Gerente del departamento que se suma (`409` si ya participa). Quitar: líder del conjunto o Administrador, solo si el subproyecto no tiene tareas y queda al menos uno.

#### `PATCH /proyectos/{id_proyecto}/estado` → `200`
```json
{ "etapa_actual": "Pruebas y Validación", "estado_proyecto": "En Revisión" }
```
Todos los campos son opcionales, pero hay que enviar al menos uno de `etapa_actual` o `estado_proyecto`. El avance se recalcula con las tareas. `fecha_real_cierre` solo se usa al pasar a `Completado`. Aplica la regla 1 y devuelve `ProyectoDetalle`. Error `422` con el motivo (salto de etapa, estatus no permitido con la lista de válidos o proyecto ya `Completado`/`Cancelado`).

---

### 6.4 Etapas del proyecto

**`EtapaRead`** (copiada de la plantilla del departamento al crear el proyecto)
```json
{ "id_etapa": 1, "id_proyecto": 1, "nombre_etapa": "Construcción y Ejecución", "orden_secuencia": 3,
  "descripcion": "Se construye: …", "estados_permitidos": ["Activo", "Pausado", "Bloqueado", "Cancelado"],
  "horas_estimadas": "120.00", "horas_efectivas_reales": "0.00",
  "fecha_inicio_est": null, "fecha_fin_est": null, "estado_etapa": "Activo" }
```

#### `PATCH /proyectos/{id_proyecto}/etapas/{id_etapa}` → `200`
Cuerpo (parcial): `horas_estimadas` (decimal ≥ 0, no nulo), `fecha_inicio_est`, `fecha_fin_est` (fin no puede ser anterior al inicio; `null` borra). El estatus no se edita aquí: lo sincroniza `PATCH /proyectos/{id}/estado`.
Errores: `404` proyecto o etapa (de otro proyecto); `422` fechas incoherentes.

#### `GET /proyectos/{id_proyecto}/etapas` → `200`
Arreglo de `EtapaRead` ordenado por `orden_secuencia`.

### 6.4.1 Configuración por departamento: etapas y etiquetas

Las edita el Gerente del departamento o el Administrador (`403` si no); cualquiera puede consultarlas. `{departamento}` es un `DepartamentoProyecto` (codificado en la URL).

#### `GET|PUT /departamentos/{departamento}/etapas` → `200`
Plantilla de etapas `[{ departamento, orden, nombre, descripcion, estados_permitidos }]`, inicialmente las cinco macro-etapas. `PUT { "etapas": [{ nombre, descripcion?, estados_permitidos }] }` reemplaza la lista (1–12, nombres únicos); solo afecta a los proyectos que se creen después. En `estados_permitidos` se eligen `En Revisión`, `Pausado`, `Bloqueado`, `Cancelado`; `Activo` siempre se permite, `Sin Iniciar` se agrega a la primera etapa y `Completado` a la última. Cada etapa de un proyecto vale 100 % / n de su avance.

#### `GET /etiquetas?departamento=` · `POST /departamentos/{departamento}/etiquetas` · `PATCH|DELETE /etiquetas/{id}`
Etiqueta `{ id_etiqueta, departamento, nombre, color }` (`color` hexadecimal `#rrggbb`, nombre único por departamento sin distinguir mayúsculas: `409`). Al eliminarla se quita de los proyectos.

---

### 6.5 Asignación de recursos

**`AsignacionRead`**
```json
{ "id_asignacion": 1, "id_proyecto": 1, "id_usuario": 2, "id_etapa": 1,
  "perfil_requerido": "Backend", "horas_en_tareas": "64.00" }
```
La asignación solo dice quién participa en qué etapa y con qué rol; no lleva horas ni dedicación. `horas_en_tareas`: horas estimadas de las tareas de esa persona en esa etapa (todas, incluidas las finalizadas); el costo se estima con ellas.

#### `POST /proyectos/{id_proyecto}/asignaciones` → `201`
| Campo | Tipo | Reglas |
| :--- | :--- | :--- |
| `id_usuario` | int | recurso activo |
| `id_etapa` | int | etapa del mismo proyecto |
| `perfil_requerido` | string | 1–100 caracteres, texto libre (rol desempeñado) |

Permiso: líder del proyecto, Gerentes o Administrador (`403`). El frontend muestra la carga actual de la persona en el periodo para decidir. Errores: `404` proyecto o etapa (de otro proyecto); `409` usuario ya asignado a esa etapa; `422` usuario inactivo o proyecto `Completado`/`Cancelado`.

#### `GET /proyectos/{id_proyecto}/asignaciones` → `200`
Arreglo de `AsignacionRead`.

---

### 6.6 Bloqueos y desfases

**Modelo.** Un bloqueo es un periodo en que una **tarea** (o, sin tarea, una etapa) no pudo avanzar. No cambia el estatus de la tarea: solo la marca y cuenta tiempo. Tres conceptos separados:
- **Bloqueo** (este recurso): causa, origen (`DTI`/`Cliente`/`Tercero`), quién lo destraba, compromiso de solución; abierto → resuelto.
- **Bloqueo automático** (`automatico: true`, causa `Dependencia Interna`): el sistema lo abre cuando una tarea `Pendiente` llega a su fecha de inicio con dependencias sin terminar (también entre subproyectos de un conjunto) y lo cierra cuando termina la última (fin = su `fecha_finalizacion`). No se crea, edita, cierra ni borra a mano (`422`). Se sincroniza al consultar tareas o bloqueos y tras cada cambio de tareas.
- **Desfase** (§6.7): días hábiles entre la fecha límite original (línea base) de la tarea y la real; se explica con sus reprogramaciones.

**Tiempo hábil.** Con el calendario laboral (§6.8) y la zona horaria de la empresa (`ZONA_HORARIA`, por defecto `America/Mexico_City`): de cada día hábil que toca el bloqueo cuentan las horas cubiertas, hasta la jornada de ese día; `dias_impacto` = Σ horas / jornada. Domingos, sábados sin horas y días inactivos no cuentan. Los bloqueos de una misma tarea se **unen** antes de sumar (dos simultáneos no cuentan doble). Un bloqueo abierto devuelve su tiempo hasta ahora.

**Permisos.** Reportar, editar y resolver: la persona asignada a la tarea o quien gestiona el proyecto (bloqueos de etapa: solo quien gestiona). Eliminar (registros equivocados): quien gestiona. Todo queda en la bitácora de la tarea (o del proyecto, si no tiene tarea) y aparece en su línea de tiempo.

**`BloqueoRead`**
```json
{ "id_bloqueo": 1, "id_proyecto": 1, "nombre_proyecto": "Portal", "id_etapa": 1, "nombre_etapa": "Diseño",
  "id_tarea": 4, "titulo_tarea": "Levantar requerimientos", "id_usuario_tarea": 2, "nombre_usuario_tarea": "Ana López",
  "causa_raiz": "Espera del Cliente", "responsable_origen": "Cliente", "descripcion": "Sin respuesta del área usuaria",
  "responsable_resolucion": "Gerencia de Compras", "fecha_compromiso": "2026-10-03", "compromiso_vencido": false,
  "nota_resolucion": "Enviaron la información", "automatico": false, "reportado_por_nombre": "Ana López",
  "fecha_inicio_bloqueo": "2026-10-01T08:00:00Z", "fecha_fin_bloqueo": "2026-10-03T20:00:00Z",
  "dias_impacto": "2.40", "horas_impacto": "21.60" }
```

#### `POST /bloqueos` → `201`
| Campo | Tipo | Obligatorio | Notas |
| :--- | :--- | :---: | :--- |
| `id_tarea` | int | sí, salvo bloqueo de etapa | tarea de proyecto no finalizada; su proyecto y etapa se toman de ella |
| `id_proyecto`, `id_etapa` | int | solo sin tarea | bloqueo que afecta a toda una etapa |
| `causa_raiz` | `CausaRaiz` | sí | no `Dependencia Interna` (la registra el sistema) |
| `responsable_origen` | `ResponsableOrigen` | sí | de quién depende destrabarlo |
| `descripcion` | string | no | qué está pasando |
| `responsable_resolucion` | string | no | quién lo destraba (persona, área o empresa) |
| `fecha_compromiso` | date | no | para cuándo se comprometió la solución (`compromiso_vencido` si pasa abierto) |
| `fecha_inicio_bloqueo` | datetime con zona | no | default: ahora; no en el futuro |
| `fecha_fin_bloqueo` | datetime con zona | no | si se envía, nace resuelto |

Errores: `403`; `404` tarea, proyecto o etapa; `422` tarea finalizada o recurrente, proyecto cerrado, fechas incoherentes.

#### `GET /bloqueos` → `200`
Query: `id_proyecto` (un conjunto incluye sus subproyectos), `departamento`, `id_etapa`, `id_tarea`, `causa_raiz`, `responsable_origen`, `abierto`, `automatico`, `limit` (máx. 200), `offset`. Abiertos primero, luego del más reciente al más antiguo.

#### `GET /bloqueos/resumen` → `200`
Query: `id_proyecto` | `departamento` (ninguno = portafolio), `desde`, `hasta` (acotan el tiempo de bloqueo). Devuelve `abiertos`, `abiertos_automaticos`, `compromisos_vencidos`, `tareas_bloqueadas`, `bloqueos_periodo`, `dias_bloqueo`/`horas_bloqueo` (suma por tarea, bloqueos unidos), `promedio_resolucion_dias`, `por_causa` y `por_origen` (`[{clave, bloqueos, dias}]`), `por_proyecto` (`abiertos`, `dias`, `desfase_dias`), `desfase` y `tareas_con_desfase` (las 15 más atrasadas).
`desfase.total` (Σ de los desfases positivos) = `por_bloqueo` (días que se movieron fechas límite por un bloqueo, por su origen) + `reprogramado_sin_bloqueo` + `ejecucion` (término real, o hoy si sigue vencida, contra la fecha límite vigente; negativo si terminó antes).

#### `GET /bloqueos/{id_bloqueo}` → `200`
`404` si no existe.

#### `PATCH /bloqueos/{id_bloqueo}` → `200`
Editables: `causa_raiz`, `responsable_origen`, `descripcion`, `responsable_resolucion`, `fecha_compromiso`, `nota_resolucion`, `fecha_inicio_bloqueo`, `fecha_fin_bloqueo` (con fin recalcula la duración). Errores: `403`; `404`; `422` automático, fechas incoherentes o campos obligatorios en `null`.

#### `POST /bloqueos/{id_bloqueo}/cerrar` → `200`
Cuerpo opcional: `{ "fecha_fin_bloqueo": "…", "nota_resolucion": "Cómo se resolvió" }` (fin por defecto: ahora). Fija `dias_impacto` y `horas_impacto`. `422` si ya estaba resuelto, es automático o el fin es anterior al inicio.

#### `DELETE /bloqueos/{id_bloqueo}` → `204`
Solo registros equivocados (quien gestiona el proyecto); un bloqueo real se resuelve. `422` si es automático.

---

### 6.7 Tareas

**`TareaRead`**
```json
{ "id_tarea": 1, "id_proyecto": 1, "nombre_proyecto": "Portal", "estado_proyecto": "Activo",
  "departamento": "Desarrollo de Software", "id_proyecto_padre": null, "id_etapa": 3, "nombre_etapa": "Construcción y Ejecución", "orden_etapa": 3,
  "id_usuario": 2, "nombre_usuario": "Ana López", "titulo": "Maquetar login", "descripcion": null,
  "horas_asignadas": "6.00", "horas_reales": null, "fecha_inicio": "2026-10-20", "fecha_fin": "2026-10-22",
  "estado": "En progreso", "fecha_creacion": "2026-10-19T18:00:00Z", "fecha_finalizacion": null,
  "num_comentarios": 0, "bloqueada": false,
  "dependencias": [{ "id_tarea": 4, "titulo": "Definir diseño", "estado": "Finalizado",
                    "id_proyecto": 1, "nombre_proyecto": "Portal", "departamento": "Desarrollo de Software" }],
  "dependientes": [{ "id_tarea": 9, "titulo": "Pruebas de login", "estado": "Pendiente",
                    "id_proyecto": 7, "nombre_proyecto": "Portal", "departamento": "Infraestructura" }] }
```
**Seguimiento** (tareas de proyecto): `fecha_inicio_base`/`fecha_fin_base` (línea base, fijada al crearla), `desfase_dias` (días hábiles de la fecha límite original a la real: su finalización o, si sigue abierta, la vigente u hoy si ya venció; positivo = atraso), `num_reprogramaciones`, `dias_bloqueada`/`horas_bloqueada` (tiempo hábil con algún bloqueo), `bloqueo_abierto` (`{id_bloqueo, causa_raiz, automatico, descripcion, desde, dias}` o null) y `periodos_bloqueo` (`[{inicio, fin, automatico, causa_raiz}]`, para el cronograma).

`departamento` es el del proyecto de la tarea (null en las generales de un conjunto y en las recurrentes); `id_proyecto_padre`, el conjunto al que pertenece su proyecto si es un subproyecto. Las tareas relacionadas traen su proyecto y departamento para identificar las de otra parte del conjunto.

**Proyectos conjuntos.** Un conjunto no tiene etapas: sus tareas propias (**generales**, p. ej. de coordinación) van con `id_etapa: null`, no consumen presupuesto ni cuentan en el avance (que se consolida de los subproyectos) y las gestiona su líder o el Administrador; su responsable debe ser líder o tener una asignación en alguno de los subproyectos. Las dependencias pueden cruzar entre el conjunto y cualquiera de sus subproyectos (no con proyectos ajenos); los ciclos se validan en todo el conjunto. En comentarios se puede mencionar a cualquier persona del conjunto.

#### `POST /proyectos/{id_proyecto}/tareas` → `201`
| Campo | Tipo | Obligatorio | Notas |
| :--- | :--- | :---: | :--- |
| `titulo` | string | sí | 1–200 |
| `descripcion` | string \| null | no | |
| `id_etapa` | int \| null | sí, salvo conjunto | etapa del mismo proyecto; en un conjunto, `null` (`422` si se envía) |
| `id_usuario` | int | sí | persona activa **con una asignación en el proyecto** (ser líder no basta); en un conjunto, asignada en algún subproyecto o líder del conjunto o de un subproyecto |
| `horas_asignadas` | decimal | sí | ≥ 0; la suma de las tareas del proyecto no puede exceder `horas_presupuestadas` (no aplica en un conjunto) |
| `fecha_inicio`, `fecha_fin` | date | sí | con ellas se reparte la carga semanal de la persona; fin no anterior al inicio; ambas dentro de las fechas del proyecto (`fecha_inicio` … comprometida o tentativa) |
| `estado` | `EstadoTarea` | no | default `Pendiente` |
| `dependencias` | int[] | no | tareas **del mismo proyecto** (en un conjunto o subproyecto, de cualquier parte del conjunto) que deben estar `Finalizado` antes de que esta salga de `Pendiente`; sin autodependencia ni ciclos (directos o indirectos) |

Permiso: líder del proyecto, Gerentes o Administrador (`403`). Errores: `404` proyecto, etapa o usuario; `422` persona inactiva o ajena al proyecto, fechas incoherentes o fuera del proyecto, presupuesto de horas excedido o proyecto `Completado`/`Cancelado`.

#### `GET /proyectos/{id_proyecto}/tareas` → `200`
Query opcional: `id_etapa`, `id_usuario`, `estado`. Ordenadas por fecha límite. En un conjunto devuelve la **vista general**: sus tareas generales y las de todos sus subproyectos (que se editan en el subproyecto).

#### `GET /tareas` → `200`
Tareas de una persona en todos sus proyectos. Sin `id_usuario`, las de quien consulta (vacío si la sesión no está ligada a una persona del Equipo). Ver las de otra persona: solo Gerentes y Administrador (`403`). Query opcional: `estado`.

#### `PATCH /tareas/{id_tarea}` → `200`
Cuerpo parcial con los campos de alta (las fechas no aceptan `null`), más `horas_reales` (≥ 0 o `null` para borrarlas; solo en tareas `Finalizado`, si no `422`). La **persona asignada** solo puede cambiar `estado` (mover la tarjeta en el kanban) y `horas_reales`; el líder, Gerentes y Administrador pueden cambiar todo. `dependencias` reemplaza la lista completa (solo quien gestiona). **Regla de dependencias:** la tarea solo puede pasar a `En progreso`, `En revisión` o `Finalizado` si todas sus dependencias están `Finalizado` (`422` que lista las pendientes); `bloqueada: true` indica que aún no puede. Agregar una dependencia a una tarea ya iniciada no la regresa a `Pendiente`. Pasar a `Finalizado` registra `fecha_finalizacion` y recalcula el avance (regla 1), lo que puede hacer avanzar la etapa o completar el proyecto. Errores: `403`; `404`; `422` como en el alta.

**Reprogramaciones y línea base.** Todo cambio de `fecha_inicio`/`fecha_fin` de una tarea de proyecto queda como reprogramación con su desfase en días hábiles. **Retrasar la fecha límite exige `motivo_cambio`** (`422` si falta); `id_bloqueo_causa` (opcional, un bloqueo de la tarea) atribuye el cambio a ese bloqueo.

#### `GET /tareas/{id_tarea}/reprogramaciones` → `200`
`[{ id_reprogramacion, fecha, actor_nombre, inicio_antes, inicio_despues, fin_antes, fin_despues, dias_habiles, motivo, id_bloqueo, causa_bloqueo, es_linea_base }]`, del más reciente al más antiguo.

#### `POST /tareas/{id_tarea}/linea-base` → `200`
`{ "motivo": "Cambio de alcance acordado" }`. Las fechas vigentes pasan a ser el plan original; el desfase se mide desde ahí y solo cuentan las reprogramaciones posteriores. Solo quien gestiona el proyecto. Devuelve `TareaRead`.

#### `DELETE /tareas/{id_tarea}` → `204`
Solo líder, Gerentes o Administrador. Recalcula el avance y elimina sus dependencias (las tareas que la esperaban quedan libres).

#### Trazabilidad, comentarios y menciones

Cada alta, edición, movimiento y baja de una tarea queda en la bitácora (`entidad = "tarea"`) con quién, cuándo y un `resumen` legible (p. ej. `Movida de «En progreso» a «Finalizado»`, `Responsable: Ana → Luis`, `Ahora depende de «Diseño»`). Una edición sin cambios reales no se registra. `TareaRead` incluye `num_comentarios`.

- `GET /tareas/{id_tarea}/actividad` → `EventoTarea[]` del más antiguo al más reciente: `{ tipo: "cambio" | "comentario", fecha, id_actor, actor_nombre, accion?, resumen?, cambios?, id_comentario?, texto?, menciones: [{ id_usuario, nombre }] }`.
- `GET /proyectos/{id_proyecto}/involucrados` → personas activas que se pueden mencionar: líder y quienes tienen asignación (`{ id_usuario, nombre, es_lider }`).
- `POST /tareas/{id_tarea}/comentarios` → `201` `EventoTarea`. Cuerpo `{ texto (1–4000), menciones: [id_usuario] }`. Comentan las personas del proyecto, Gerentes y Administrador (`403`); solo se puede mencionar a involucrados (`422`). Mencionarse a sí mismo no notifica; los ids repetidos cuentan una vez.
- `DELETE /comentarios/{id_comentario}` → `204`. Autor, Gerentes o Administrador.

**Notificaciones** (cada mención es una):
- `GET /notificaciones?solo_no_leidas=&limit=` → `{ no_leidas, items: [{ id_mencion, leida, fecha, autor_nombre, texto, id_tarea, titulo_tarea, id_proyecto, nombre_proyecto }] }` de quien consulta (vacío si la sesión no está ligada a una persona).
- `POST /notificaciones/{id_mencion}/leer` → `204` (solo las propias; `404` si no). `POST /notificaciones/leer-todas` → `204`.

---

### 6.8 Configuración (calendario laboral)

Calcula las horas presupuestadas de los proyectos: Σ horas de cada día entre el inicio y el fin del proyecto (ambos incluidos): lunes a viernes `horas_entre_semana`, sábado `horas_sabado` (0 = no cuenta), domingo nunca, y los `dias_inactivos` no cuentan. Por defecto: 8 h y 5 h, sin días desactivados.

**`ConfiguracionLaboral`**
```json
{ "horas_entre_semana": "8", "horas_sabado": "5", "dias_inactivos": ["2026-12-25", "2026-12-26"] }
```

#### `GET /configuracion` → `200`
#### `PUT /configuracion` → `200`
Cuerpo: `ConfiguracionLaboral` completo (horas entre 0 y 24; `dias_inactivos` cualquier fecha, se ordenan y deduplican). Solo Administrador (`403`). Recalcula el presupuesto de los proyectos abiertos en cálculo automático y devuelve además `proyectos_recalculados` y `proyectos_excedidos` (los que quedaron con más horas en tareas que presupuesto; no se bloquea).

#### `GET /configuracion/horas-laborales?desde=&hasta=` → `200`
`{ "desde", "hasta", "horas", "dias_laborables" }` según el calendario vigente. Para mostrar el cálculo antes de guardar un proyecto.

---

## 7. Flujos típicos para el frontend

**Alta inicial de datos maestros:** `POST /empresas` → `POST /areas`; `GET /puestos` (o `POST /puestos`) → `POST /usuarios` (líder y recursos).

**Crear y planificar un proyecto:**
1. `GET /usuarios?activo=true` (cualquier persona activa puede liderar) y `GET /empresas` para poblar los selectores.
2. `POST /proyectos` con empresas impactadas.
3. `PATCH /proyectos/{id}/etapas/{id_etapa}` para planificar horas y fechas de cada etapa.
4. `POST /proyectos/{id}/asignaciones` por cada recurso.
5. `POST /proyectos/{id}/tareas` por cada tarea de cada etapa.
6. Cada persona mueve sus tareas con `PATCH /tareas/{id}` (`GET /tareas` para su tablero); al finalizar las de la etapa actual el proyecto avanza solo. `PATCH /proyectos/{id}/estado` queda para regresar de etapa, avanzar una etapa sin tareas o cambiar el estatus.

**Tablero de portafolio:** `GET /proyectos?semaforo=Rojo&id_empresa=1&limit=50&offset=0`; para el conteo por semáforo, una llamada por valor leyendo solo `total` (con `limit=1`).

**Gestión de bloqueos de un proyecto:** `GET /bloqueos?id_proyecto=1&abierto=true` para los activos; `POST /bloqueos` al reportar uno; `POST /bloqueos/{id}/cerrar` al resolverlo.

---

## 8. Funcionalidad pendiente (sin endpoints todavía)

Las tablas y modelos ya existen en la base de datos, pero la API aún no las expone: **solicitudes de demanda**, **business case**, **evaluación financiera**, **hitos/entregables**, **retrabajo**, **actualizaciones de avance**, **compromisos del cliente**, **realización de valor**, **dependencias entre proyectos** y las vistas analíticas de capacidad/productividad. Tampoco hay autenticación ni listados de asignaciones por usuario (carga de capacidad). Conviene que el frontend deje estas áreas desacopladas hasta que se definan.

---

### 6.10 Tareas recurrentes (operación)

Operación del día a día que no es un proyecto. Una **tarea recurrente** (`Diaria`, `Semanal` o `Mensual`) pertenece a una persona y genera una `Tarea` por periodo: cada día laborable del calendario (§6.8), cada semana (lunes → su último día laborable) o cada mes (día 1 → su último día laborable). Las tareas generadas son tareas normales (`TareaRead` con `id_proyecto`/`id_etapa` en null y `id_recurrente`, `frecuencia`, `periodo`, `etiquetas`): kanban, horas reales, comentarios y menciones (`GET /tareas/{id}/involucrados`), sin etapa ni dependencias. Se generan al llegar su periodo (al consultar tareas o capacidad); los futuros se proyectan en la capacidad de **operación** = capacidad semanal × (100 − `porcentaje_proyectos`), que `GET /capacidad` devuelve aparte (`capacidad_operacion`, `horas_operacion_disponibles`, `horas_operacion_asignadas`, `utilizacion_operacion`).

Permisos: cada quien gestiona las suyas; el Gerente, las de su departamento; el Administrador, todas (y así se filtra lo que cada quien ve).

| Endpoint | Notas |
| :--- | :--- |
| `GET /tareas-recurrentes/tareas` | Panel: tareas generadas. Query: `id_usuario`, `departamento`, `frecuencia`, `etiquetas` (repetible), `estado`, `id_recurrente`, `desde`/`hasta` (traslape con sus fechas), `vencidas`. Máx. 500 |
| `GET /tareas-recurrentes` | Plantillas (+ `tareas_abiertas`). Query: `id_usuario`, `departamento`, `frecuencia`, `activa`, `etiquetas` |
| `POST /tareas-recurrentes` | `{ titulo, descripcion?, id_usuario, frecuencia, horas_por_periodo, fecha_inicio (≤ 31 días atrás), fecha_fin?, etiquetas? }` (etiquetas del departamento del responsable). Genera de inmediato los periodos ya llegados |
| `PATCH /tareas-recurrentes/{id}` | Aplica a las tareas futuras. `activa: false` la pausa; al reanudarla se retoma en el periodo actual |
| `DELETE /tareas-recurrentes/{id}` | Borra la plantilla **con todas sus tareas**; para conservarlas, pausarla |
| `PATCH` / `DELETE /tareas/{id}` | En una tarea generada: editarla o quitar solo ese periodo (no se vuelve a generar) |

### 6.11 Equipos de trabajo (workspaces)

Agrupan a personas de **cualquier departamento** y los proyectos de una línea de negocio (p. ej. Servicios Corporativos en Software, Combustibles). **Solo organizan** (filtros y métricas): los permisos siguen por rol y departamento. Una persona puede estar en varios equipos; un proyecto pertenece a uno o a ninguno (`proyecto.id_equipo_trabajo`), y un subproyecto siempre al de su conjunto (cambiarlo en el subproyecto da `422`; cambiarlo en el conjunto lo aplica a todos).

**`EquipoTrabajoRead`**
```json
{ "id_equipo_trabajo": 1, "nombre": "Servicios Corporativos en Software", "descripcion": "Proyectos del corporativo",
  "color": "#2563eb", "fecha_creacion": "2026-10-22T18:00:00Z",
  "miembros": [{ "id_usuario": 2, "nombre": "Ana López", "departamento": "Desarrollo de Software" }],
  "proyectos": 5, "proyectos_abiertos": 3, "proyectos_en_riesgo": 1, "bloqueos_abiertos": 2 }
```

| Método y ruta | Descripción |
| :--- | :--- |
| `GET /equipos-trabajo` | Todos (query `id_usuario`: solo los de esa persona), con personas y conteos (`proyectos` cuenta un conjunto una vez). |
| `POST /equipos-trabajo` | `{ nombre, descripcion?, color (#rrggbb), miembros: [ids] }`. Nombre único sin distinguir mayúsculas (`409`). Gerentes o Administrador. |
| `GET /equipos-trabajo/{id}` | Uno. |
| `PATCH /equipos-trabajo/{id}` | Campos parciales; `miembros` reemplaza la lista. Gerentes o Administrador. |
| `DELETE /equipos-trabajo/{id}` | Sus proyectos quedan sin equipo; las personas no cambian. Gerentes o Administrador. |

Filtro `id_equipo_trabajo` en `GET /proyectos`, `GET /bloqueos` y `GET /bloqueos/resumen`; `ProyectoCreate`/`ProyectoUpdate` aceptan `id_equipo_trabajo` (null = sin equipo) y `TareaRead` lo incluye (el de su proyecto). Los cambios quedan en la bitácora (`entidad = "equipo_trabajo"`).


### 6.12 Asistente de IA (`/asistente`)

#### `POST /asistente/token` → `200` `{token, expira}`
Token de **solo lectura** para que el agente (Google ADK) consulte la API en nombre de quien pregunta. Características:
- Dura `ASISTENTE_TOKEN_MINUTOS` (15).
- Solo admite `GET` sobre `/sesion`, `/perfil`, `/usuarios`, `/proyectos`, `/tareas`, `/bloqueos`, `/capacidad`, `/equipos-trabajo` y `/asistente/senales`; lo demás responde `403`.
- Respeta la visibilidad por rol (§2.5).
- No se puede pedir con otro token del asistente.

Para pruebas locales: `docker compose exec api python -m app.cli.token_asistente <correo>`.

#### `POST /asistente/chat` `{mensaje, id_conversacion?}` → `200` NDJSON
Pregunta al asistente; la respuesta llega por partes, una línea JSON por evento:
- `{"tipo":"sesion","id"}`: identificador de la conversación; se reenvía para continuarla;
- `{"tipo":"estado","texto"}`: qué está consultando;
- `{"tipo":"texto","delta"}`: fragmento de la respuesta;
- `{"tipo":"final","texto"}`: texto completo; reemplaza los fragmentos;
- `{"tipo":"fin"}` o `{"tipo":"error","mensaje"}`.

Cada pregunta lleva al agente (`ASISTENTE_URL`, con la clave compartida `ASISTENTE_CLAVE`) un token nuevo de solo lectura de quien pregunta; el navegador nunca lo ve. Límite: `ASISTENTE_MAX_PREGUNTAS` (30) por persona cada 10 minutos (`429`). Sin `ASISTENTE_URL` → `503`. `GET /sesion` incluye `asistente_disponible`.

#### `GET /asistente/senales` → `200` `SenalesAsistente`
`{generado, alcance, senales: [{tipo, severidad: alta|media, titulo, detalle, id_proyecto?, id_tarea?, id_usuario?, enlace?}]}`. Son hechos calculados con reglas dentro de lo visible para la persona, ordenados por severidad:

| `tipo` | Qué detecta | Severidad alta si |
| :--- | :--- | :--- |
| `proyecto_en_riesgo` | Proyecto con semáforo rojo o amarillo | El semáforo es rojo |
| `tarea_vencida` | Tarea abierta después de su fecha límite | Lleva más de 3 días vencida |
| `bloqueo_abierto` | Bloqueo reportado que sigue abierto | Lleva más de 3 días hábiles, o su compromiso ya venció |
| `espera_dependencia` | Tarea que espera a que otras terminen | — |
| `desfase` | Tarea con 5 o más días hábiles de atraso contra el plan | El atraso llega a 10 días hábiles |
| `sobrecarga` | Persona con más de 100 % de carga esta semana; quien gestiona ve a su gente, los demás solo su propia carga | La carga pasa de 120 % |
