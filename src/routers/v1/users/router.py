from fastapi import APIRouter

from .dependencies import UserServiceDep
from .schemas import UserIn, UserOut

user_router = APIRouter(prefix='/users', tags=['users'])


@user_router.post('', response_model=UserOut)
async def create_user(user: UserIn, service: UserServiceDep):
    return await service.register(user)
