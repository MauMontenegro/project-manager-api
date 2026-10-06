from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.models.enums import PerfilTecnico
from app.models.organizacion import Area, Empresa, Usuario
from app.schemas.organizacion import AreaCreate, EmpresaCreate
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate


async def crear_empresa(db: AsyncSession, data: EmpresaCreate) -> Empresa:
    if await db.scalar(select(Empresa.id_empresa).where(Empresa.nombre_empresa == data.nombre_empresa)):
        raise ConflictError(f"Ya existe la empresa '{data.nombre_empresa}'")
    empresa = Empresa(**data.model_dump())
    db.add(empresa)
    await db.commit()
    await db.refresh(empresa)
    return empresa


async def listar_empresas(db: AsyncSession) -> list[Empresa]:
    return list(await db.scalars(select(Empresa).order_by(Empresa.nombre_empresa)))


async def crear_area(db: AsyncSession, data: AreaCreate) -> Area:
    if await db.get(Empresa, data.id_empresa) is None:
        raise NotFoundError(f"Empresa con id {data.id_empresa} no existe")
    if await db.scalar(select(Area.id_area).where(Area.codigo_area == data.codigo_area)):
        raise ConflictError(f"Ya existe un área con código '{data.codigo_area}'")
    area = Area(**data.model_dump())
    db.add(area)
    await db.commit()
    await db.refresh(area)
    return area


async def listar_areas(db: AsyncSession, id_empresa: int | None = None) -> list[Area]:
    stmt = select(Area).order_by(Area.nombre_area)
    if id_empresa is not None:
        stmt = stmt.where(Area.id_empresa == id_empresa)
    return list(await db.scalars(stmt))


async def _validar_correo_libre(db: AsyncSession, correo: str, excluir_id: int | None = None) -> None:
    stmt = select(Usuario.id_usuario).where(Usuario.correo == correo)
    if excluir_id is not None:
        stmt = stmt.where(Usuario.id_usuario != excluir_id)
    if await db.scalar(stmt) is not None:
        raise ConflictError(f"El correo '{correo}' ya está registrado")


async def crear_usuario(db: AsyncSession, data: UsuarioCreate) -> Usuario:
    if await db.get(Area, data.id_area) is None:
        raise NotFoundError(f"Área con id {data.id_area} no existe")
    await _validar_correo_libre(db, data.correo)
    usuario = Usuario(**data.model_dump())
    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)
    return usuario


async def obtener_usuario(db: AsyncSession, id_usuario: int) -> Usuario:
    usuario = await db.get(Usuario, id_usuario)
    if usuario is None:
        raise NotFoundError(f"Usuario con id {id_usuario} no existe")
    return usuario


async def listar_usuarios(
    db: AsyncSession,
    *,
    id_area: int | None = None,
    perfil_tecnico: PerfilTecnico | None = None,
    activo: bool | None = None,
    busqueda: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Usuario]:
    stmt = select(Usuario)
    if id_area is not None:
        stmt = stmt.where(Usuario.id_area == id_area)
    if perfil_tecnico is not None:
        stmt = stmt.where(Usuario.perfil_tecnico == perfil_tecnico.value)
    if activo is not None:
        stmt = stmt.where(Usuario.activo == activo)
    if busqueda:
        patron = f"%{busqueda}%"
        stmt = stmt.where(Usuario.nombre.ilike(patron) | Usuario.correo.ilike(patron))
    stmt = stmt.order_by(Usuario.nombre).limit(limit).offset(offset)
    return list(await db.scalars(stmt))


async def actualizar_usuario(db: AsyncSession, id_usuario: int, data: UsuarioUpdate) -> Usuario:
    usuario = await obtener_usuario(db, id_usuario)
    cambios = data.model_dump(exclude_unset=True)

    for campo, valor in cambios.items():
        if valor is None:
            raise BusinessRuleError(f"{campo} no puede ser nulo")

    if "correo" in cambios:
        await _validar_correo_libre(db, cambios["correo"], excluir_id=id_usuario)
    if "id_area" in cambios and await db.get(Area, cambios["id_area"]) is None:
        raise NotFoundError(f"Área con id {cambios['id_area']} no existe")

    for campo, valor in cambios.items():
        setattr(usuario, campo, valor)

    await db.commit()
    await db.refresh(usuario)
    return usuario


async def desactivar_usuario(db: AsyncSession, id_usuario: int) -> None:
    """Baja lógica: el usuario puede estar referenciado por proyectos, solicitudes y avances (FK RESTRICT)."""
    usuario = await obtener_usuario(db, id_usuario)
    usuario.activo = False
    await db.commit()
