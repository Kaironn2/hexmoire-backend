from typing import Literal

from pydantic import BaseModel


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
