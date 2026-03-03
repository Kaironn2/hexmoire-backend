from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.session import get_session

DbSessionDep = Annotated[AsyncSession, Depends(get_session)]
