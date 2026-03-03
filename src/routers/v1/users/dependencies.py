from typing import Annotated

from fastapi import Depends

from src.dependencies.database import DbSessionDep
from src.repositories.sql.user import UserRepository

from .service import UserService


def get_user_repository(session: DbSessionDep) -> UserRepository:
    return UserRepository(session)


def get_user_service(user_repo: UserRepository = Depends(get_user_repository)) -> UserService:
    return UserService(user_repo)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
