from fastapi import HTTPException, status

from src.core.db.models.users.user import User
from src.core.security.hash import Hasher
from src.repositories.sql.user import UserRepository

from .schemas import UserIn, UserOut


class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def register(self, data: UserIn) -> UserOut:
        existing = await self.user_repo.get_by_username_or_email(data.username, data.email)
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, detail='Usúario ou email já existem.')

        user = User(username=data.username, email=data.email, password=Hasher.get_password_hash(data.password))

        created_user = await self.user_repo.create(user)
        return UserOut.model_validate(created_user)
