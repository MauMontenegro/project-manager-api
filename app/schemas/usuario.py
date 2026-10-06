from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import PerfilTecnico


class UsuarioBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    correo: EmailStr = Field(max_length=150)
    perfil_tecnico: PerfilTecnico
    capacidad_horas_semanales: Decimal = Field(ge=0, le=999, max_digits=5, decimal_places=2)
    id_area: int


class UsuarioCreate(UsuarioBase):
    activo: bool = True


class UsuarioUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    correo: EmailStr | None = Field(default=None, max_length=150)
    perfil_tecnico: PerfilTecnico | None = None
    capacidad_horas_semanales: Decimal | None = Field(default=None, ge=0, le=999, max_digits=5, decimal_places=2)
    id_area: int | None = None
    activo: bool | None = None


class UsuarioRead(UsuarioBase):
    model_config = ConfigDict(from_attributes=True)

    id_usuario: int
    activo: bool
