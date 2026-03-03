from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.core.settings import DATABASE_URL, config


def create_engine_from_url(database_url: str) -> AsyncEngine:
    if database_url.startswith('sqlite'):
        return create_async_engine(
            database_url,
            echo=config.DATABASE_ECHO,
            future=True,
            connect_args={'check_same_thread': False},
        )
    else:
        return create_async_engine(
            database_url,
            echo=config.DATABASE_ECHO,
            future=True,
            pool_size=config.DATABASE_POOL_SIZE,
            max_overflow=config.DATABASE_POOL_OVERFLOW,
            pool_recycle=config.DATABASE_POOL_RECYCLE,
            pool_pre_ping=True,
        )


engine = create_engine_from_url(DATABASE_URL)
