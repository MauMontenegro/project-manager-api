from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

Correo = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=150)]
Password = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class LoginIn(BaseModel):
    correo: Correo
    password: Password


class SesionToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira: datetime
    # La persona entró con una contraseña temporal: debe cambiarla antes de usar la app.
    password_temporal: bool


class CambiarPasswordIn(BaseModel):
    actual: Password
    nueva: Password


class RestablecerPasswordIn(BaseModel):
    """Sin `nueva`, la API genera una contraseña temporal."""

    nueva: Password | None = None


class PasswordTemporal(BaseModel):
    password_temporal: str
