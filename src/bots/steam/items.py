from datetime import datetime
from typing import Literal

from pydantic import BaseModel, RootModel


class SteamCookie(BaseModel):
    name: str
    value: str
    domain: str
    path: str
    expires: float | int
    httpOnly: bool
    secure: bool
    sameSite: Literal['None', 'Lax', 'Strict']


class SteamCookies(BaseModel):
    cookies: list[SteamCookie]


class Achievement(BaseModel):
    username: str
    game: str | None
    title: str | None
    description: str | None
    unlock_time: datetime | None
    current_progress: float | None
    total_progress: float | None
    language: str | None
    url: str


class AchievementList(RootModel):
    root: list[Achievement]
