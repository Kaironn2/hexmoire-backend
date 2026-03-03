from fastapi import APIRouter

from .users.router import user_router

v1_router = APIRouter(prefix='/v1', tags=['v1'])

v1_router.include_router(user_router)