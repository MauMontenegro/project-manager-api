from fastapi import APIRouter, Depends

from app.api.v1.endpoints import (
    asistente, auth, bloqueos, catalogos, colaboracion, configuracion, departamentos, equipo, equipos_trabajo, proyectos, recurrentes, tareas,
    usuarios,
)
from app.core.security import get_actor

# Toda la API exige sesión; las reglas por rol se aplican en los servicios.
api_router = APIRouter(dependencies=[Depends(get_actor)])
api_router.include_router(auth.router)
api_router.include_router(asistente.router)
api_router.include_router(catalogos.router)
api_router.include_router(usuarios.router)
api_router.include_router(equipo.router)
api_router.include_router(equipos_trabajo.router)
api_router.include_router(proyectos.router)
api_router.include_router(bloqueos.router)
api_router.include_router(tareas.router)
api_router.include_router(recurrentes.router)
api_router.include_router(configuracion.router)
api_router.include_router(departamentos.router)
api_router.include_router(colaboracion.router)

# Sin sesión: solo el inicio de sesión.
public_router = APIRouter()
public_router.include_router(auth.publico)
