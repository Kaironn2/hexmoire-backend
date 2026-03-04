import asyncio
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class RateLimiter:
    """Controls concurrency globally and per-domain using asyncio semaphores.

    Usage:
        limiter = RateLimiter(max_concurrent=20, max_per_domain=5)
        async with limiter.acquire("https://example.com/page"):
            ...  # request happens here
    """

    def __init__(self, max_concurrent: int = 20, max_per_domain: int = 5):
        self._global_semaphore = asyncio.Semaphore(max_concurrent)
        self._max_per_domain = max_per_domain
        self._domain_semaphores: dict[str, asyncio.Semaphore] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def extract_domain(url: str) -> str:
        parsed = urlparse(url)
        return parsed.netloc or parsed.hostname or url

    async def _get_domain_semaphore(self, domain: str) -> asyncio.Semaphore:
        if domain not in self._domain_semaphores:
            async with self._lock:
                if domain not in self._domain_semaphores:
                    self._domain_semaphores[domain] = asyncio.Semaphore(self._max_per_domain)
        return self._domain_semaphores[domain]

    class _AcquireContext:
        """Async context manager that holds both the global and domain semaphores."""

        def __init__(self, global_sem: asyncio.Semaphore, domain_sem: asyncio.Semaphore):
            self._global = global_sem
            self._domain = domain_sem

        async def __aenter__(self):
            await self._global.acquire()
            try:
                await self._domain.acquire()
            except BaseException:
                self._global.release()
                raise
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            self._domain.release()
            self._global.release()

    async def acquire(self, url: str) -> _AcquireContext:
        domain = self.extract_domain(url)
        domain_sem = await self._get_domain_semaphore(domain)
        return self._AcquireContext(self._global_semaphore, domain_sem)
