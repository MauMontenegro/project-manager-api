from fastapi import APIRouter

from app.api.v1.endpoints import bloqueos, catalogos, proyectos, usuarios

api_router = APIRouter()
api_router.include_router(catalogos.router)
api_router.include_router(usuarios.router)
api_router.include_router(proyectos.router)
api_router.include_router(bloqueos.router)
