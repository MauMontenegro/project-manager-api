# Referencia del Backend y la API — Petroil Project Manager

Documento de referencia para el desarrollo del frontend. Describe convenciones, enums, modelos de datos, reglas de negocio y todos los endpoints disponibles.

- **Base URL (local):** `http://localhost:8000`
- **Prefijo de la API:** `/api/v1`
- **Documentación interactiva (OpenAPI):** `/docs` (Swagger) y `/openapi.json` (útil para generar clientes tipados)
- **Health check:** `GET /health` → `{"status": "ok"}`
- **Formato:** JSON (`Content-Type: application/json`)
- **Autenticación:** no implementada todavía. Todos los endpoints son públicos.
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
| Enums | string exacto, **con tildes y mayúsculas** | `"Iniciación"` |

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
| `422` (regla de negocio) | Transición de estado inválida, usuario inactivo, proyecto cerrado, bloqueo ya cerrado, fechas incoherentes, campo nulo no permitido | `string` |
| `422` (validación de esquema) | Tipo, rango o enum inválido en el cuerpo/query | `array` de objetos `{loc, msg, type}` (formato estándar de FastAPI) |

El frontend debe distinguir ambos 422 comprobando si `detail` es `string` o `array`.

```json
{ "detail": "Transición no permitida: 'Iniciación' → 'Cierre'. Estados permitidos: Cancelado, Pausado, Planeación" }
```

---

## 3. Enumeraciones

Los valores se envían y reciben **tal cual** se muestran aquí.

| Enum | Valores |
| :--- | :--- |
| `PerfilTecnico` | `Análisis Funcional`, `Backend`, `Frontend`, `Testing`, `Infraestructura`, `Líder`, `Cliente` |
| `EstadoProyecto` | `Iniciación`, `Planeación`, `Ejecución`, `Cierre`, `Cancelado`, `Pausado` |
| `Semaforo` | `Verde`, `Amarillo`, `Rojo` |
| `NivelImpacto` | `Alto`, `Medio`, `Bajo` |
| `NombreEtapa` | `Análisis`, `Arquitectura`, `Desarrollo`, `Testing`, `Implementación` |
| `EstadoEtapa` | `Pendiente`, `En Curso`, `Detenido`, `Completado` |
| `CausaRaiz` (bloqueos) | `Cambio de Prioridad`, `Dependencia Externa`, `Falta de Información`, `Recurso Reasignado`, `Incidente Operativo`, `Cambio de Alcance`, `Retrabajo`, `Espera del Cliente`, `Decisión Pendiente` |
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

Orden de creación obligatorio (por FKs): **Empresa → Área → Usuario → Proyecto → Etapa → Asignación / Bloqueo**.

---

## 5. Reglas de negocio

1. **Ciclo de vida del proyecto.** Un proyecto nace en `Iniciación`. Transiciones permitidas:

   | Desde | Hacia |
   | :--- | :--- |
   | `Iniciación` | `Planeación`, `Pausado`, `Cancelado` |
   | `Planeación` | `Ejecución`, `Pausado`, `Cancelado` |
   | `Ejecución` | `Cierre`, `Pausado`, `Cancelado` |
   | `Pausado` | `Planeación`, `Ejecución`, `Cancelado` |
   | `Cierre`, `Cancelado` | _(estados finales, ninguna)_ |

   Al pasar a `Cierre` se fija `fecha_real_cierre` (la enviada o, por defecto, hoy). El estado **no** se edita con `PATCH /proyectos/{id}`; solo con `PATCH /proyectos/{id}/estado`. Se recomienda que la UI muestre solo las transiciones válidas.
2. **Líder activo.** `lider_id` debe ser un usuario existente y `activo = true`.
3. **Solicitud única.** Una solicitud de demanda solo puede originar un proyecto; al crearlo, la solicitud pasa a `En Ejecución`.
4. **Empresas impactadas.** No se pueden repetir empresas en un mismo proyecto; todas deben existir.
5. **Etapas.** `orden_secuencia` es único dentro del proyecto.
6. **Asignaciones.** La etapa debe pertenecer al proyecto, el usuario debe estar activo, el proyecto no puede estar en `Cierre` ni `Cancelado`, y un usuario no puede asignarse dos veces a la misma etapa.
7. **Bloqueos.** La etapa debe pertenecer al proyecto. `dias_impacto = (fecha_fin − fecha_inicio)` en días, con 2 decimales, calculado por el backend (nunca se envía). Un bloqueo sin `fecha_fin_bloqueo` está **abierto** y su `dias_impacto` es `null`.
8. **Usuarios.** El correo es único. `DELETE` es una **baja lógica** (`activo = false`): el usuario sigue apareciendo en los listados salvo que se filtre por `activo=true`.
9. **Portafolio por empresa.** `id_empresa` coincide con proyectos donde la empresa es una de las **impactadas** o la **solicitante** de la demanda de origen.

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

#### `POST /areas` → `201`
```json
{ "id_empresa": 1, "nombre_area": "DTI", "codigo_area": "DTI-01" }
```
Respuesta `AreaRead`: el mismo cuerpo más `id_area`.
Errores: `404` empresa inexistente; `409` `codigo_area` duplicado.

#### `GET /areas` → `200`
Query: `id_empresa` (opcional). Arreglo de `AreaRead`, ordenado por nombre.

---

### 6.2 Usuarios (recursos)

**`UsuarioRead`**
```json
{ "id_usuario": 2, "nombre": "Beto Dev", "correo": "beto@petroil.com", "perfil_tecnico": "Backend",
  "capacidad_horas_semanales": "40.00", "id_area": 1, "activo": true }
```

#### `POST /usuarios` → `201`
| Campo | Tipo | Obligatorio | Reglas |
| :--- | :--- | :---: | :--- |
| `nombre` | string | sí | 1–150 caracteres |
| `correo` | email | sí | único, máx. 150 |
| `perfil_tecnico` | `PerfilTecnico` | sí | |
| `capacidad_horas_semanales` | decimal | sí | 0–999, 2 decimales |
| `id_area` | int | sí | debe existir |
| `activo` | bool | no | default `true` |

Errores: `404` área inexistente; `409` correo duplicado.

#### `GET /usuarios` → `200`
Query: `id_area`, `perfil_tecnico`, `activo`, `q` (busca en nombre o correo, sin distinguir mayúsculas), `limit`, `offset`. Arreglo de `UsuarioRead` ordenado por nombre.

#### `GET /usuarios/{id_usuario}` → `200`
`404` si no existe.

#### `PATCH /usuarios/{id_usuario}` → `200`
Cualquier subconjunto de los campos de creación (incluido `activo`). `null` no está permitido en ningún campo (`422`). Errores: `404`, `409` (correo en uso).

#### `DELETE /usuarios/{id_usuario}` → `204`
Baja lógica. Sin cuerpo.

---

### 6.3 Proyectos y portafolio

**`ProyectoRead`** (usado en el listado)
```json
{ "id_proyecto": 1, "nombre_proyecto": "Portal", "problema_oportunidad": "...", "objetivo": "...",
  "alcance": "...", "fuera_de_alcance": "...", "fecha_tentativa": null, "fecha_comprometida": "2026-12-15",
  "fecha_real_cierre": null, "id_solicitud": null, "lider_id": 1,
  "estado_proyecto": "Iniciación", "semaforo": "Amarillo" }
```

**`ProyectoDetalle`** = `ProyectoRead` + `empresas_impactadas`:
```json
"empresas_impactadas": [ { "id_empresa": 1, "nivel_impacto": "Alto", "notas_impacto": null } ]
```

#### `POST /proyectos` → `201` (devuelve `ProyectoDetalle`)
| Campo | Tipo | Obligatorio | Notas |
| :--- | :--- | :---: | :--- |
| `nombre_proyecto` | string | sí | 1–200 |
| `problema_oportunidad`, `objetivo`, `alcance`, `fuera_de_alcance` | string | sí | no vacíos |
| `lider_id` | int | sí | usuario activo |
| `id_solicitud` | int \| null | no | ver regla 3 |
| `fecha_tentativa`, `fecha_comprometida` | date \| null | no | |
| `semaforo` | `Semaforo` | no | default `Verde` |
| `empresas_impactadas` | array | no | `[{ id_empresa, nivel_impacto, notas_impacto? }]`, sin empresas repetidas |

`estado_proyecto` no se envía: siempre inicia en `Iniciación`.
Errores: `404` (líder, solicitud o empresa inexistente); `409` solicitud ya usada; `422` líder inactivo o empresas repetidas.

#### `GET /proyectos` → `200` — Portafolio
Query (todos opcionales y combinables): `semaforo`, `id_empresa`, `estado` (`EstadoProyecto`), `lider_id`, `limit` (default 50, máx. 200), `offset`.
Respuesta `{ items: ProyectoRead[], total, limit, offset }`, ordenado del más reciente al más antiguo. `total` es el conteo con los filtros aplicados (úselo para paginar).

#### `GET /proyectos/{id_proyecto}` → `200`
`ProyectoDetalle`. `404` si no existe.

#### `PATCH /proyectos/{id_proyecto}` → `200`
Campos editables: `nombre_proyecto`, `problema_oportunidad`, `objetivo`, `alcance`, `fuera_de_alcance`, `fecha_tentativa`, `fecha_comprometida`, `semaforo`, `lider_id`. Las fechas sí aceptan `null` para borrarlas; el resto no. Devuelve `ProyectoDetalle`.

#### `PATCH /proyectos/{id_proyecto}/estado` → `200`
```json
{ "estado_proyecto": "Cierre", "fecha_real_cierre": "2026-12-20" }
```
`fecha_real_cierre` es opcional y solo se usa al pasar a `Cierre`. Devuelve `ProyectoDetalle`. Error `422` con la lista de estados permitidos si la transición no es válida.

---

### 6.4 Etapas del proyecto

**`EtapaRead`**
```json
{ "id_etapa": 1, "id_proyecto": 1, "nombre_etapa": "Desarrollo", "orden_secuencia": 1,
  "horas_estimadas": "120.00", "horas_efectivas_reales": "0.00",
  "fecha_inicio_est": null, "fecha_fin_est": null, "estado_etapa": "Pendiente" }
```

#### `POST /proyectos/{id_proyecto}/etapas` → `201`
Cuerpo: `nombre_etapa` (`NombreEtapa`), `orden_secuencia` (int > 0), `horas_estimadas` (decimal ≥ 0), `fecha_inicio_est?`, `fecha_fin_est?` (fin no puede ser anterior al inicio). La etapa inicia en `Pendiente`.
Errores: `404` proyecto; `409` `orden_secuencia` repetido en el proyecto.

#### `GET /proyectos/{id_proyecto}/etapas` → `200`
Arreglo de `EtapaRead` ordenado por `orden_secuencia`.

---

### 6.5 Asignación de recursos

**`AsignacionRead`**
```json
{ "id_asignacion": 1, "id_proyecto": 1, "id_usuario": 2, "id_etapa": 1,
  "perfil_requerido": "Backend", "horas_asignadas": "80.00", "porcentaje_utilizacion": "50.00" }
```

#### `POST /proyectos/{id_proyecto}/asignaciones` → `201`
| Campo | Tipo | Reglas |
| :--- | :--- | :--- |
| `id_usuario` | int | usuario activo |
| `id_etapa` | int | etapa del mismo proyecto |
| `perfil_requerido` | string | 1–100 caracteres, texto libre (rol desempeñado) |
| `horas_asignadas` | decimal | > 0 |
| `porcentaje_utilizacion` | decimal | 0–100 (lo informa el cliente; el backend no lo calcula) |

Errores: `404` proyecto o etapa (de otro proyecto); `409` usuario ya asignado a esa etapa; `422` usuario inactivo o proyecto en `Cierre`/`Cancelado`.

#### `GET /proyectos/{id_proyecto}/asignaciones` → `200`
Arreglo de `AsignacionRead`.

---

### 6.6 Bloqueos e interrupciones

**`BloqueoRead`**
```json
{ "id_bloqueo": 1, "id_proyecto": 1, "id_etapa": 1, "causa_raiz": "Espera del Cliente",
  "responsable_origen": "Cliente", "fecha_inicio_bloqueo": "2026-10-01T08:00:00Z",
  "fecha_fin_bloqueo": "2026-10-03T20:00:00Z", "dias_impacto": "2.50" }
```

#### `POST /bloqueos` → `201`
| Campo | Tipo | Obligatorio | Notas |
| :--- | :--- | :---: | :--- |
| `id_proyecto` | int | sí | |
| `id_etapa` | int | sí | debe pertenecer al proyecto |
| `causa_raiz` | `CausaRaiz` | sí | |
| `responsable_origen` | `ResponsableOrigen` | sí | |
| `fecha_inicio_bloqueo` | datetime con zona | no | default: ahora |
| `fecha_fin_bloqueo` | datetime con zona | no | si se envía, se calcula `dias_impacto` |

Errores: `404` proyecto o etapa; `422` fin anterior al inicio.

#### `GET /bloqueos` → `200`
Query: `id_proyecto`, `id_etapa`, `causa_raiz`, `responsable_origen`, `abierto` (`true` = sin fecha de fin, `false` = cerrados), `limit`, `offset`. Arreglo de `BloqueoRead`, del más reciente al más antiguo.

#### `GET /bloqueos/{id_bloqueo}` → `200`
`404` si no existe.

#### `PATCH /bloqueos/{id_bloqueo}` → `200`
Campos editables: `causa_raiz`, `responsable_origen`, `fecha_inicio_bloqueo`, `fecha_fin_bloqueo`. `dias_impacto` se recalcula automáticamente si hay fecha de fin y se pone en `null` si no la hay. Errores: `404`; `422` fechas incoherentes o campos obligatorios en `null`.

#### `POST /bloqueos/{id_bloqueo}/cerrar` → `200`
Cuerpo opcional: `{ "fecha_fin_bloqueo": "2026-10-06T12:00:00Z" }` (por defecto: ahora). Libera el bloqueo y calcula `dias_impacto`. Error `422` si ya estaba cerrado o si la fecha es anterior al inicio.

#### `DELETE /bloqueos/{id_bloqueo}` → `204`
Eliminación física.

---

## 7. Flujos típicos para el frontend

**Alta inicial de datos maestros:** `POST /empresas` → `POST /areas` → `POST /usuarios` (líder y recursos).

**Crear y planificar un proyecto:**
1. `GET /usuarios?perfil_tecnico=Líder&activo=true` y `GET /empresas` para poblar los selectores.
2. `POST /proyectos` con empresas impactadas.
3. `POST /proyectos/{id}/etapas` por cada fase.
4. `POST /proyectos/{id}/asignaciones` por cada recurso.
5. `PATCH /proyectos/{id}/estado` → `Planeación` → `Ejecución`.

**Tablero de portafolio:** `GET /proyectos?semaforo=Rojo&id_empresa=1&limit=50&offset=0`; para el conteo por semáforo, una llamada por valor leyendo solo `total` (con `limit=1`).

**Gestión de bloqueos de un proyecto:** `GET /bloqueos?id_proyecto=1&abierto=true` para los activos; `POST /bloqueos` al reportar uno; `POST /bloqueos/{id}/cerrar` al resolverlo.

---

## 8. Funcionalidad pendiente (sin endpoints todavía)

Las tablas y modelos ya existen en la base de datos, pero la API aún no las expone: **solicitudes de demanda**, **business case**, **evaluación financiera**, **hitos/entregables**, **retrabajo**, **actualizaciones de avance**, **compromisos del cliente**, **realización de valor**, **dependencias entre proyectos** y las vistas analíticas de capacidad/productividad. Tampoco hay autenticación ni listados de asignaciones por usuario (carga de capacidad). Conviene que el frontend deje estas áreas desacopladas hasta que se definan.
