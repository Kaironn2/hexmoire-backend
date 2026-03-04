from datetime import datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db.base import Base
from src.core.db.models.mixins.primary_key import UuidPrimaryKeyMixin
from src.core.db.models.mixins.timestamp import TimeStampMixin


class SteamAchievement(Base, UuidPrimaryKeyMixin, TimeStampMixin):
    __tablename__ = 'steam_achievements'

    __table_args__ = (
        UniqueConstraint(
            'username',
            'game',
            'title',
            name='uq_user_game_title'
        ),
    )

    username: Mapped[str]
    game: Mapped[str]
    title: Mapped[str]
    description: Mapped[Optional[str]] = mapped_column(nullable=True)
    unlock_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    current_progress: Mapped[Optional[float]] = mapped_column(nullable=True)
    total_progress: Mapped[Optional[float]] = mapped_column(nullable=True)
    language: Mapped[Optional[str]] = mapped_column(nullable=True)
    url: Mapped[Optional[str]] = mapped_column(nullable=True)
