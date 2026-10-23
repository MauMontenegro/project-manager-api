from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActor
from app.models.enums import DepartamentoProyecto
from app.schemas.departamento import EtiquetaIn, EtiquetaRead, PlantillaEtapaRead, PlantillaEtapasIn
from app.services import departamento_service

router = APIRouter(tags=["Departamentos"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/departamentos/{departamento}/etapas", response_model=list[PlantillaEtapaRead])
async def obtener_etapas(departamento: DepartamentoProyecto, db: DbSession):
    """Etapas que reciben los proyectos nuevos del departamento."""
    etapas = await departamento_service.plantilla(db, departamento)
    await db.commit()
    return etapas


@router.put("/departamentos/{departamento}/etapas", response_model=list[PlantillaEtapaRead])
async def guardar_etapas(departamento: DepartamentoProyecto, data: PlantillaEtapasIn, db: DbSession, actor: CurrentActor):
    """Reemplaza las etapas del departamento (Gerente del departamento o Administrador). Los proyectos
    existentes conservan las etapas con las que se crearon."""
    return await departamento_service.guardar_plantilla(db, actor, departamento, data)


@router.get("/etiquetas", response_model=list[EtiquetaRead])
async def listar_etiquetas(db: DbSession, departamento: DepartamentoProyecto | None = None):
    return await departamento_service.listar_etiquetas(db, departamento)


@router.post(
    "/departamentos/{departamento}/etiquetas", response_model=EtiquetaRead, status_code=status.HTTP_201_CREATED
)
async def crear_etiqueta(departamento: DepartamentoProyecto, data: EtiquetaIn, db: DbSession, actor: CurrentActor):
    return await departamento_service.crear_etiqueta(db, actor, departamento, data)


@router.patch("/etiquetas/{id_etiqueta}", response_model=EtiquetaRead)
async def actualizar_etiqueta(id_etiqueta: int, data: EtiquetaIn, db: DbSession, actor: CurrentActor):
    return await departamento_service.actualizar_etiqueta(db, actor, id_etiqueta, data)


@router.delete("/etiquetas/{id_etiqueta}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_etiqueta(id_etiqueta: int, db: DbSession, actor: CurrentActor):
    """La etiqueta se quita también de los proyectos que la tenían."""
    await departamento_service.eliminar_etiqueta(db, actor, id_etiqueta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
