import asyncio
import logging
from typing import Literal

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from src.infra.browser.config import BrowserConfig

logger = logging.getLogger(__name__)


class BrowserClient:
    """A managed Playwright browser client with concurrency control.

    Features:
        - Configurable browser type (chromium/firefox/webkit)
        - Page-level concurrency limiting via semaphore
        - Managed lifecycle with async context manager
        - Convenience methods for common automation patterns

    Usage:
        async with BrowserClient(BrowserConfig(headless=True)) as client:
            page = await client.new_page()
            await page.goto("https://example.com")
            content = await page.content()
            await page.close()
    """

    def __init__(self, config: BrowserConfig | None = None):
        self._config = config or BrowserConfig()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page_semaphore = asyncio.Semaphore(self._config.max_concurrent_pages)

    # -- Lifecycle --

    async def start(self) -> None:
        """Launch the browser and create a default context."""
        self._playwright = await async_playwright().start()

        launcher = getattr(self._playwright, self._config.browser_type)
        launch_kwargs: dict = {
            'headless': self._config.headless,
            'slow_mo': self._config.slow_mo,
        }
        if self._config.proxy:
            launch_kwargs['proxy'] = self._config.proxy

        self._browser = await launcher.launch(**launch_kwargs)
        assert self._browser is not None

        context_kwargs: dict = {
            'viewport': {'width': self._config.viewport_width, 'height': self._config.viewport_height},
            'ignore_https_errors': self._config.ignore_https_errors,
        }
        if self._config.user_agent:
            context_kwargs['user_agent'] = self._config.user_agent

        self._context = await self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(self._config.default_timeout)
        logger.info('BrowserClient started (%s, headless=%s)', self._config.browser_type, self._config.headless)

    async def close(self) -> None:
        """Close the browser and Playwright instance."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info('BrowserClient closed')

    async def __aenter__(self) -> 'BrowserClient':
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    # -- Page management --

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError('BrowserClient not started. Call start() or use as async context manager.')
        return self._context

    async def new_page(self) -> Page:
        """Create a new page, respecting the max concurrent pages limit.

        The semaphore is acquired here. Call `release_page(page)` or `page.close()`
        when you're done to free the slot.
        """
        await self._page_semaphore.acquire()
        try:
            page = await self.context.new_page()
            page.on('close', lambda _: self._page_semaphore.release())
            return page
        except BaseException:
            self._page_semaphore.release()
            raise

    # -- Convenience methods --

    async def goto(
        self,
        url: str,
        *,
        timeout: float | None = None,
        wait_until: Literal['commit', 'domcontentloaded', 'load', 'networkidle'] | None = None,
        referer: str | None = None,
    ) -> Page:
        """Open a new page and navigate to the URL.

        Returns the Page for further interaction. Remember to close it when done.
        """
        page = await self.new_page()
        await page.goto(url, timeout=timeout, wait_until=wait_until, referer=referer)
        return page

    async def get_content(
        self,
        url: str,
        *,
        timeout: float | None = None,
        wait_until: Literal['commit', 'domcontentloaded', 'load', 'networkidle'] | None = None,
        referer: str | None = None,
    ) -> str:
        """Navigate to a URL and return the page HTML content."""
        page = await self.goto(url, timeout=timeout, wait_until=wait_until, referer=referer)
        try:
            return await page.content()
        finally:
            await page.close()

    async def screenshot(
        self,
        url: str,
        path: str,
        full_page: bool = True,
        *,
        timeout: float | None = None,
        wait_until: Literal['commit', 'domcontentloaded', 'load', 'networkidle'] | None = None,
        referer: str | None = None,
    ) -> bytes:
        """Navigate to a URL and take a screenshot."""
        page = await self.goto(url, timeout=timeout, wait_until=wait_until, referer=referer)
        try:
            return await page.screenshot(path=path, full_page=full_page)
        finally:
            await page.close()

    async def pdf(
        self,
        url: str,
        path: str,
        *,
        timeout: float | None = None,
        wait_until: Literal['commit', 'domcontentloaded', 'load', 'networkidle'] | None = None,
        referer: str | None = None,
    ) -> bytes:
        """Navigate to a URL and generate a PDF (Chromium only)."""
        page = await self.goto(url, timeout=timeout, wait_until=wait_until, referer=referer)
        try:
            return await page.pdf(path=path)
        finally:
            await page.close()
