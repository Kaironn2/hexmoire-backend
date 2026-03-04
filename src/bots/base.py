from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from src.infra.http.client import HttpClient
from src.infra.http.config import HttpClientConfig, HttpConfigOverrides


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
