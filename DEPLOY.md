# Despliegue en Google Cloud Run desde GitLab CI/CD

Flujo: `git push` → GitLab CI → Cloud Build (imagen en Artifact Registry `ms`) → Cloud Run Job (`alembic upgrade head`) → Cloud Run (servicio).

| Rama | Servicio Cloud Run | Deploy |
| :--- | :--- | :--- |
| `development` | `project-manager-api-dev` | automático |
| `master` | `project-manager-api` | **manual** (botón en GitLab) |

- Proyecto GCP: `innovacion-futuro` · Región: `us-central1` · Repositorio de imágenes: `ms`.
- La base de datos es externa; se conecta con la variable `APP_DATABASE_URL`.
- Las migraciones corren como Cloud Run Job antes de cada deploy (no al arrancar el contenedor).

## Paso 1. Verificar la cuenta de servicio `cloud-run-gitlab`

Es la cuenta que usará GitLab para desplegar. Comprueba sus roles:

```bash
gcloud projects get-iam-policy innovacion-futuro \
  --flatten="bindings[].members" \
  --filter="bindings.members:cloud-run-gitlab@innovacion-futuro.iam.gserviceaccount.com" \
  --format="value(bindings.role)"
```

Debe tener, como mínimo: `roles/run.admin`, `roles/cloudbuild.builds.editor`, `roles/artifactregistry.writer`, `roles/storage.objectAdmin`, `roles/serviceusage.serviceUsageConsumer`, `roles/logging.viewer` y `roles/iam.serviceAccountUser`. Si falta alguno y no puedes asignarlo, pídeselo a DevOps. Si el comando da `PERMISSION_DENIED`, salta al paso 2: los errores del primer pipeline te dirán qué falta.

## Paso 2. Crear la clave de la cuenta

```bash
mkdir -p ~/gcp-keys && chmod 700 ~/gcp-keys
gcloud iam service-accounts keys create ~/gcp-keys/cloud-run-gitlab.json \
  --iam-account=cloud-run-gitlab@innovacion-futuro.iam.gserviceaccount.com
```

Crear una clave nueva no afecta a las existentes. Si da `PERMISSION_DENIED` o un error de política de organización, pide a DevOps que te entregue la clave. La clave es un secreto: no la subas al repositorio ni la pegues en chats.

## Paso 3. Variables de GitLab

Proyecto → *Settings → CI/CD → Variables → Add variable*:

| Variable | Tipo | Valor | Opciones |
| :--- | :--- | :--- | :--- |
| `GCP_SA_KEY` | **File** | contenido del JSON (`pbcopy < ~/gcp-keys/cloud-run-gitlab.json`) | Protected |
| `GCP_PROJECT_ID` | Variable | `innovacion-futuro` | |
| `GCP_REGION` | Variable | `us-central1` | |
| `APP_DATABASE_URL` | Variable | ver abajo | Protected |
| `CORS_ORIGINS` | Variable | `["https://tu-frontend.com"]` (JSON) | |
| `RUN_EXTRA_FLAGS` | Variable (opcional) | flags extra de `gcloud run`, p. ej. red VPC | |

`APP_DATABASE_URL`:

```
postgresql+asyncpg://USUARIO:CLAVE@HOST:PUERTO/BASE
```

- Codifica en la clave los caracteres especiales: `!` → `%21`, `@` → `%40`, `/` → `%2F`, `%` → `%25`.
- Agrega `?ssl=require` solo si el servidor soporta TLS. Pruébalo con `psql "host=... sslmode=require"`.
- No se puede marcar como *Masked* si contiene `%`; pide una contraseña sin caracteres especiales si quieres enmascararla.
- Para `development` y `production` deberían ser **bases distintas**. Si solo tienes una, evita desplegar `master` apuntando a la misma hasta que exista otra.

Luego, en *Settings → Repository → Protected branches*, verifica que `development` y `master` estén protegidas (las variables Protected solo llegan a esas ramas).

## Paso 4. Primer despliegue

```bash
git add -A && git commit -m "Agrega pipeline de despliegue a Cloud Run"
git push origin development
```

En *Build → Pipelines* verás `test → build → migrate → deploy`. Para producción: merge a `master` y pulsa **▶ deploy:production**.

## Paso 5. Verificar

El servicio se crea **sin acceso público** (`--no-allow-unauthenticated`):

```bash
URL=$(gcloud run services describe project-manager-api-dev --region us-central1 --format='value(status.url)')
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" $URL/health
# o un túnel local autenticado:
gcloud run services proxy project-manager-api-dev --region us-central1 --port 8080
```

## Paso 6. Limpieza

Cuando `GCP_SA_KEY` esté cargada en GitLab, borra la copia local: `rm ~/gcp-keys/cloud-run-gitlab.json`.

## Decisión pendiente: acceso desde el frontend

La API aún **no tiene autenticación propia**. Un navegador no puede enviar un token IAM de Google, así que:

1. **Mantenerla privada** y que el frontend la consuma desde un backend/proxy con identidad de Google (o IAP).
2. **Hacerla pública** cambiando `--no-allow-unauthenticated` por `--allow-unauthenticated` en `.gitlab-ci.yml`. No lo hagas en producción hasta implementar autenticación: cualquiera con la URL podría leer y escribir datos.

## Problemas comunes

- **Job sin runner / `docker` no encontrado:** el pipeline usa imágenes (`google/cloud-sdk`, `python`); necesita un runner con executor Docker o Kubernetes. Revisa *Settings → CI/CD → Runners*.
- **Variables vacías en el job:** la rama no está protegida y la variable sí.
- **`PERMISSION_DENIED` en `gcloud builds submit` o `run deploy`:** faltan roles en `cloud-run-gitlab` (paso 1). Si el error nombra a la cuenta de Compute (`842403446987-compute@...`), esa cuenta, que ejecuta Cloud Build, necesita `roles/artifactregistry.writer` y `roles/logging.logWriter`.
- **El servicio no conecta a la BD:** revisa que `APP_DATABASE_URL` esté completa y bien codificada, y que la BD sea alcanzable desde Cloud Run (firewall, VPC egress).
- **Migración fallida:** el deploy no continúa; revisa los logs del job `*-migrate` en Cloud Run → Jobs.
