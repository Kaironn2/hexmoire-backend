from pydantic import BaseModel


class BrowserConfig(BaseModel):
    """Configuration for the Playwright browser client.

    Attributes:
        headless: Run browser in headless mode.
        browser_type: Browser engine — "chromium", "firefox", or "webkit".
        default_timeout: Default timeout for page operations in milliseconds.
        viewport_width: Default viewport width in pixels.
        viewport_height: Default viewport height in pixels.
        user_agent: Optional custom user agent string.
        proxy: Optional proxy config (e.g. {"server": "http://proxy:8080"}).
        ignore_https_errors: Whether to ignore HTTPS certificate errors.
        max_concurrent_pages: Maximum number of concurrent pages/tabs.
        slow_mo: Slow down operations by this amount of milliseconds (useful for debugging).
    """

    headless: bool = True
    browser_type: str = 'chromium'
    default_timeout: float = 30000
    viewport_width: int = 1920
    viewport_height: int = 1080
    user_agent: str | None = None
    proxy: dict[str, str] | None = None
    ignore_https_errors: bool = False
    max_concurrent_pages: int = 5
    slow_mo: float = 0
