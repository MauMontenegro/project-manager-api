from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models.enums import Departamento, NivelSkill, RolSistema, TipoRecurso

NombreSkill = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class SkillAsignada(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nombre: NombreSkill
    nivel: NivelSkill = NivelSkill.INTERMEDIO


def _sin_duplicados(skills: list[SkillAsignada]) -> list[SkillAsignada]:
    """Quita repetidos sin distinguir mayúsculas, conservando la primera aparición."""
    vistos: set[str] = set()
    unicos = []
    for skill in skills:
        if skill.nombre.casefold() not in vistos:
            vistos.add(skill.nombre.casefold())
            unicos.append(skill)
    return unicos


Skills = Annotated[list[SkillAsignada], Field(max_length=30), AfterValidator(_sin_duplicados)]
Capacidad = Annotated[Decimal, Field(ge=0, le=999, max_digits=5, decimal_places=2)]
Porcentaje = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
CostoHora = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]


class UsuarioCreate(BaseModel):
    """Las reglas que dependen del tipo de recurso (correo/puesto obligatorios, proveedor
    en externos) se validan en el servicio, porque también aplican a las ediciones parciales."""

    tipo_recurso: TipoRecurso = TipoRecurso.INTERNO
    nombre: str = Field(min_length=1, max_length=150)
    correo: EmailStr | None = Field(default=None, max_length=150)
    id_puesto: int | None = None
    departamento: Departamento
    id_jefe: int | None = None
    rol: RolSistema = RolSistema.USUARIO
    skills: Skills = []
    capacidad_horas_semanales: Capacidad
    porcentaje_proyectos: Porcentaje = Decimal(100)
    costo_hora: CostoHora | None = None
    proveedor: str | None = Field(default=None, max_length=150)
    fecha_fin_contrato: date | None = None
    activo: bool = True


class UsuarioUpdate(BaseModel):
    """Campos omitidos no cambian. `null` solo se acepta en los opcionales."""

    tipo_recurso: TipoRecurso | None = None
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    correo: EmailStr | None = Field(default=None, max_length=150)
    id_puesto: int | None = None
    departamento: Departamento | None = None
    id_jefe: int | None = None
    rol: RolSistema | None = None
    skills: Skills | None = None
    capacidad_horas_semanales: Capacidad | None = None
    porcentaje_proyectos: Porcentaje | None = None
    costo_hora: CostoHora | None = None
    proveedor: str | None = Field(default=None, max_length=150)
    fecha_fin_contrato: date | None = None
    activo: bool | None = None


class PerfilUpdate(BaseModel):
    """Lo que cada persona puede cambiar de sí misma. Puesto, rol, capacidad y demás los define su gerente."""

    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    skills: Skills | None = None


class UsuarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_usuario: int
    tipo_recurso: TipoRecurso
    nombre: str
    correo: str | None
    # Pueden ser nulos en personas registradas antes de existir puesto/departamento.
    id_puesto: int | None
    departamento: Departamento | None
    id_jefe: int | None
    rol: RolSistema
    skills: list[SkillAsignada]
    capacidad_horas_semanales: Decimal
    porcentaje_proyectos: Decimal
    # Solo visible para Administrador y Gerentes.
    costo_hora: Decimal | None
    proveedor: str | None
    fecha_fin_contrato: date | None
    activo: bool
    # Ya puede entrar con contraseña (la contraseña en sí nunca sale de la API).
    tiene_password: bool = False


class PuestoCreate(BaseModel):
    nombre_puesto: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class PuestoRead(PuestoCreate):
    model_config = ConfigDict(from_attributes=True)

    id_puesto: int
