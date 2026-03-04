from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

from src.infra.http.config import HttpClientConfig
from src.infra.browser.config import BrowserConfig

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / 'data'


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    PROD: bool = False

    # Database
    DATABASE_USER: str = 'postgres'
    DATABASE_PASSWORD: str = 'postgres'
    DATABASE_HOST: str = 'localhost'
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = 'postgres'
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 10
    DATABASE_POOL_OVERFLOW: int = 5
    DATABASE_POOL_RECYCLE: int = 3600

    # HTTP Client (global defaults)
    HTTP_MAX_CONCURRENT: int = 20
    HTTP_MAX_PER_DOMAIN: int = 5
    HTTP_TIMEOUT: float = 30.0
    HTTP_RETRIES: int = 3
    HTTP_RETRY_BACKOFF: float = 1.0
    HTTP_PROXY: str | None = None
    HTTP_VERIFY_SSL: bool = True

    # Browser / Playwright (global defaults)
    BROWSER_HEADLESS: bool = True
    BROWSER_TYPE: str = 'chromium'
    BROWSER_DEFAULT_TIMEOUT: float = 30000
    BROWSER_MAX_CONCURRENT_PAGES: int = 5

    # Redis / TaskIQ
    REDIS_URL: str = 'redis://localhost:6379/0'

    # Steam
    STEAM_USERNAME: str = ''
    STEAM_PASSWORD: str = ''

    @property
    def http_config(self) -> HttpClientConfig:
        """Build the global HttpClientConfig from env settings."""
        return HttpClientConfig(
            max_concurrent=self.HTTP_MAX_CONCURRENT,
            max_per_domain=self.HTTP_MAX_PER_DOMAIN,
            timeout=self.HTTP_TIMEOUT,
            retries=self.HTTP_RETRIES,
            retry_backoff=self.HTTP_RETRY_BACKOFF,
            proxy=self.HTTP_PROXY,
            verify_ssl=self.HTTP_VERIFY_SSL,
        )

    @property
    def browser_config(self) -> BrowserConfig:
        """Build the global BrowserConfig from env settings."""
        return BrowserConfig(
            headless=self.BROWSER_HEADLESS,
            browser_type=self.BROWSER_TYPE,
            default_timeout=self.BROWSER_DEFAULT_TIMEOUT,
            max_concurrent_pages=self.BROWSER_MAX_CONCURRENT_PAGES,
        )


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
