from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Petroil Project Manager API"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    POSTGRES_USER: str = "petroil"
    POSTGRES_PASSWORD: str = "petroil"
    POSTGRES_DB: str = "petroil"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    # Zona horaria de la empresa: define dónde empieza y termina cada día al medir bloqueos en días hábiles.
    ZONA_HORARIA: str = "America/Mexico_City"

    # Autenticación: correo y contraseña (sesiones firmadas por esta API) y, opcionalmente, Firebase Auth
    # (Google / Microsoft). Desactivada, toda petición actúa como un Administrador local: útil solo en desarrollo.
    AUTH_ENABLED: bool = False
    # Clave para firmar las sesiones (HS256). Obligatoria con AUTH_ENABLED: genera una con
    # `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Cambiarla cierra todas las sesiones.
    SECRET_KEY: str = ""
    # Duración de una sesión iniciada con contraseña.
    SESION_HORAS: int = 12
    # Vida del token que la app entrega al asistente de IA (solo lectura, en nombre de la persona).
    ASISTENTE_TOKEN_MINUTOS: int = 15
    # Servidor del agente (project-manager-agent). Vacío: el asistente no está disponible en la app.
    ASISTENTE_URL: str = ""
    ASISTENTE_CLAVE: str = ""
    # En Cloud Run el agente es privado: la API se identifica con su cuenta de servicio (ID token de Google).
    ASISTENTE_IAM: bool = False
    # Preguntas por persona en una ventana de 10 minutos (freno ante abuso y costo).
    ASISTENTE_MAX_PREGUNTAS: int = 30
    FIREBASE_PROJECT_ID: str = "innovacion-futuro"
    # Correos que entran como Administrador aunque aún no existan en el Equipo (arranque inicial).
    BOOTSTRAP_ADMIN_EMAILS: list[str] = []
    # Solo con AUTH_ENABLED=false: id de la persona del Equipo con la que actúa la sesión local
    # con el rol de acceso de esa persona (cambiándolo se prueba cada perfil). Vacío: "Administrador local", sin persona.
    LOCAL_ID_USUARIO: int | None = None

    @field_validator("LOCAL_ID_USUARIO", mode="before")
    @classmethod
    def _vacio_es_none(cls, v):
        return None if v in ("", None) else v

    @field_validator("SECRET_KEY")
    @classmethod
    def _clave_segura(cls, v: str, info):
        if info.data.get("AUTH_ENABLED") and len(v) < 32:
            raise ValueError("Con AUTH_ENABLED=true define SECRET_KEY (al menos 32 caracteres aleatorios)")
        return v

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.POSTGRES_HOST.startswith("/"):
            # Socket Unix (Cloud SQL en Cloud Run: /cloudsql/PROYECTO:REGION:INSTANCIA)
            url = URL.create(
                "postgresql+asyncpg",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                database=self.POSTGRES_DB,
                query={"host": self.POSTGRES_HOST},
            )
        else:
            url = URL.create(
                "postgresql+asyncpg",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                database=self.POSTGRES_DB,
            )
        return url.render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
