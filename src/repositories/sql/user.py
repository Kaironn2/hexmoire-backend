from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models.users.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        return await self.session.scalar(select(User).where(User.id == user_id))

    async def get_by_email(self, email: str) -> Optional[User]:
        return await self.session.scalar(select(User).where(User.email == email))

    async def get_by_username(self, username: str) -> Optional[User]:
        return await self.session.scalar(select(User).where(User.username == username))

    async def get_by_username_or_email(self, username: str, email: str) -> Optional[User]:
        return await self.session.scalar(select(User).where((User.username == username) | (User.email == email)))

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def list_all(self, limit: int = 50, offset: int = 0) -> tuple[list[User], int]:
        total = await self.session.scalar(select(func.count()).select_from(User))
        result = await self.session.scalars(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset))
        return list(result.all()), total or 0
