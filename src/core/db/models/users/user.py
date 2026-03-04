from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db.base import Base
from src.core.db.models.mixins.primary_key import UuidPrimaryKeyMixin
from src.core.db.models.mixins.timestamp import TimeStampMixin


class User(Base, UuidPrimaryKeyMixin, TimeStampMixin):
    __tablename__ = 'users'

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, server_default='true')
