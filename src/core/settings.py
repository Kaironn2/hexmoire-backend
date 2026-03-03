from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    PROD: bool = False

    DATABASE_USER: str = 'postgres'
    DATABASE_PASSWORD: str = 'postgres'
    DATABASE_HOST: str = 'localhost'
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = 'postgres'
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 10
    DATABASE_POOL_OVERFLOW: int = 5
    DATABASE_POOL_RECYCLE: int = 3600


config = Config()


def get_database_url(config: Config) -> URL:
    return URL.create(
        drivername='postgresql+asyncpg',
        username=config.DATABASE_USER,
        password=config.DATABASE_PASSWORD,
        host=config.DATABASE_HOST,
        port=config.DATABASE_PORT,
        database=config.DATABASE_NAME,
    )


if config.PROD:
    DATABASE_URL = get_database_url(config)
else:
    DATABASE_URL = 'sqlite+aiosqlite:///./db.db'
