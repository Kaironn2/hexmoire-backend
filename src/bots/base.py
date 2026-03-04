from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from src.infra.http.client import HttpClient
from src.infra.http.config import HttpClientConfig, HttpConfigOverrides
from src.infra.browser.client import BrowserClient


class BaseCrawler(ABC):
    """Base class for crawlers that use httpx + lxml.

    Subclass this and implement `run()` with your crawling logic.

    Config override:
        Set `http_config_overrides` as a class variable to customize the HTTP client
        for this specific bot. The overrides are merged on top of the global config.

    Example:
        @register_bot()
        class MyCrawler(BaseCrawler):
            http_config_overrides = {"max_per_domain": 2, "timeout": 60.0}

            async def run(self) -> list[dict]:
                tree = await self.http.get_html("https://example.com")
                titles = tree.xpath("//h1/text()")
                return [{"title": t} for t in titles]
    """

    http_config_overrides: ClassVar[HttpConfigOverrides] = {}

    def __init__(self, http: HttpClient):
        self.http = http

    @classmethod
    def create(cls, global_config: HttpClientConfig) -> BaseCrawler:
        """Factory: create a bot with its own HttpClient if overrides exist, or reuse global."""
        if cls.http_config_overrides:
            config = global_config.model_copy(update=cls.http_config_overrides)
            return cls(http=HttpClient(config))
        return cls(http=HttpClient(global_config))

    @abstractmethod
    async def run(self) -> Any:
        """Execute the crawling logic. Must be implemented by subclasses."""
        ...


class BaseAutomation(ABC):
    """Base class for automations that use Playwright.

    Subclass this and implement `run()` with your automation logic.
    The BrowserClient is injected and handles page concurrency, lifecycle, etc.

    Example:
        @register_bot()
        class MyAutomation(BaseAutomation):
            async def run(self) -> str:
                page = await self.browser.goto("https://example.com")
                await page.fill("#search", "query")
                await page.click("button[type=submit]")
                content = await page.content()
                await page.close()
                return content
    """

    def __init__(self, browser: BrowserClient):
        self.browser = browser

    @abstractmethod
    async def run(self) -> Any:
        """Execute the automation logic. Must be implemented by subclasses."""
        ...


class HybridBot(ABC):
    """Base class for bots that need both HTTP and browser capabilities.

    Use this when a bot needs to combine fast HTTP requests (e.g. API calls,
    lightweight page fetches) with browser automation (e.g. JavaScript-rendered pages,
    form submissions).

    Example:
        @register_bot()
        class MyBot(HybridBot):
            http_config_overrides = {"proxy": "http://bot-proxy:8080"}

            async def run(self) -> dict:
                resp = await self.http.get("https://api.example.com/data")
                data = resp.json()
                page = await self.browser.goto("https://app.example.com")
                await page.wait_for_selector(".loaded")
                content = await page.content()
                await page.close()
                return {"api": data, "page": content}
    """

    http_config_overrides: ClassVar[HttpConfigOverrides] = {}

    def __init__(self, http: HttpClient, browser: BrowserClient):
        self.http = http
        self.browser = browser

    @classmethod
    def create(cls, global_config: HttpClientConfig, browser: BrowserClient) -> HybridBot:
        """Factory: create a bot with its own HttpClient if overrides exist."""
        if cls.http_config_overrides:
            config = global_config.model_copy(update=cls.http_config_overrides)
            return cls(http=HttpClient(config), browser=browser)
        return cls(http=HttpClient(global_config), browser=browser)

    @abstractmethod
    async def run(self) -> Any:
        """Execute the bot logic. Must be implemented by subclasses."""
        ...
