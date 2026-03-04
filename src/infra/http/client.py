import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from httpx._types import (
    AuthTypes,
    CookieTypes,
    HeaderTypes,
    QueryParamTypes,
    RequestContent,
    RequestData,
    RequestExtensions,
    RequestFiles,
    TimeoutTypes,
)
from lxml import html as lxml_html
from lxml.html import HtmlElement

from src.infra.http.config import HttpClientConfig
from src.infra.http.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class HttpClient:
    """configurable httpx client

    Features:
        - Global and per-domain concurrency control
        - Automatic retry with exponential backoff
        - Proxy support
        - Convenience method for parsing HTML with lxml
        - Async context manager for clean resource management

    Usage:
        config = HttpClientConfig(max_concurrent=10, max_per_domain=3)
        async with HttpClient(config) as client:
            response = await client.get("https://example.com")
            tree = await client.get_html("https://example.com")
    """

    def __init__(self, config: HttpClientConfig | None = None):
        self._config = config or HttpClientConfig()
        self._rate_limiter = RateLimiter(
            max_concurrent=self._config.max_concurrent,
            max_per_domain=self._config.max_per_domain,
        )
        self._client: httpx.AsyncClient | None = None

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self._config.timeout),
            headers=self._config.default_headers,
            proxy=self._config.proxy,
            follow_redirects=self._config.follow_redirects,
            verify=self._config.verify_ssl,
        )

    # -- Lifecycle --

    async def start(self) -> None:
        if self._client is None:
            self._client = self._build_client()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> 'HttpClient':
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    # -- Internal helpers --

    @staticmethod
    def _build_request_kwargs(
        *,
        params: QueryParamTypes | None,
        headers: HeaderTypes | None,
        cookies: CookieTypes | None,
        content: RequestContent | None,
        data: RequestData | None,
        files: RequestFiles | None,
        json: Any | None,
        auth: AuthTypes | None,
        timeout: TimeoutTypes | None,
        follow_redirects: bool | None,
        extensions: RequestExtensions | None,
    ) -> dict[str, Any]:
        """Build a kwargs dict for httpx, including only explicitly provided values.

        Parameters left as ``None`` are omitted so that httpx falls back to its
        client-level defaults (e.g. timeout, follow_redirects, auth).
        """
        kwargs: dict[str, Any] = {}
        if params is not None:
            kwargs['params'] = params
        if headers is not None:
            kwargs['headers'] = headers
        if cookies is not None:
            kwargs['cookies'] = cookies
        if content is not None:
            kwargs['content'] = content
        if data is not None:
            kwargs['data'] = data
        if files is not None:
            kwargs['files'] = files
        if json is not None:
            kwargs['json'] = json
        if auth is not None:
            kwargs['auth'] = auth
        if timeout is not None:
            kwargs['timeout'] = timeout
        if follow_redirects is not None:
            kwargs['follow_redirects'] = follow_redirects
        if extensions is not None:
            kwargs['extensions'] = extensions
        return kwargs

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float | None:
        """Extract Retry-After header value in seconds, if present."""
        header = response.headers.get('Retry-After')
        if header is None:
            return None
        try:
            return float(header)
        except ValueError:
            return None

    # -- Core request --

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        content: RequestContent | None = None,
        data: RequestData | None = None,
        files: RequestFiles | None = None,
        json: Any | None = None,
        auth: AuthTypes | None = None,
        timeout: TimeoutTypes | None = None,
        follow_redirects: bool | None = None,
        extensions: RequestExtensions | None = None,
    ) -> httpx.Response:
        """Execute an HTTP request with rate limiting and retry logic.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: The target URL.
            params: Query parameters.
            headers: Request headers.
            cookies: Request cookies.
            content: Raw request body (bytes/str/stream).
            data: Form-encoded request body.
            files: Multipart file uploads.
            json: JSON-serialisable request body.
            auth: Authentication credentials or handler.
            timeout: Request timeout override.
            follow_redirects: Whether to follow HTTP redirects.
            extensions: Low-level httpx transport extensions.

        Returns:
            httpx.Response

        Raises:
            httpx.HTTPStatusError: If the response has an error status after all retries.
            httpx.TimeoutException: If the request times out after all retries.
        """
        if self._client is None:
            await self.start()

        assert self._client is not None

        request_kwargs = self._build_request_kwargs(
            params=params,
            headers=headers,
            cookies=cookies,
            content=content,
            data=data,
            files=files,
            json=json,
            auth=auth,
            timeout=timeout,
            follow_redirects=follow_redirects,
            extensions=extensions,
        )

        last_exception: Exception | None = None
        attempts = self._config.retries + 1

        for attempt in range(1, attempts + 1):
            ctx = await self._rate_limiter.acquire(url)
            async with ctx:
                try:
                    response = await self._client.request(method, url, **request_kwargs)

                    if response.status_code in self._config.retry_status_codes and attempt < attempts:
                        retry_after = self._parse_retry_after(response)
                        delay = retry_after or (self._config.retry_backoff * (2 ** (attempt - 1)))
                        logger.warning(
                            'Retryable status %s for %s %s (attempt %d/%d, delay %.1fs)',
                            response.status_code,
                            method,
                            url,
                            attempt,
                            attempts,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    return response

                except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
                    last_exception = exc
                    if attempt < attempts:
                        delay = self._config.retry_backoff * (2 ** (attempt - 1))
                        logger.warning(
                            '%s for %s %s (attempt %d/%d, delay %.1fs)',
                            type(exc).__name__,
                            method,
                            url,
                            attempt,
                            attempts,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise

        raise last_exception  # type: ignore[misc]

    # -- Convenience methods --

    async def get(
        self,
        url: str,
        *,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        content: RequestContent | None = None,
        data: RequestData | None = None,
        files: RequestFiles | None = None,
        json: Any | None = None,
        auth: AuthTypes | None = None,
        timeout: TimeoutTypes | None = None,
        follow_redirects: bool | None = None,
        extensions: RequestExtensions | None = None,
    ) -> httpx.Response:
        return await self.request(
            'GET', url,
            params=params, headers=headers, cookies=cookies,
            content=content, data=data, files=files, json=json,
            auth=auth, timeout=timeout,
            follow_redirects=follow_redirects, extensions=extensions,
        )

    async def post(
        self,
        url: str,
        *,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        content: RequestContent | None = None,
        data: RequestData | None = None,
        files: RequestFiles | None = None,
        json: Any | None = None,
        auth: AuthTypes | None = None,
        timeout: TimeoutTypes | None = None,
        follow_redirects: bool | None = None,
        extensions: RequestExtensions | None = None,
    ) -> httpx.Response:
        return await self.request(
            'POST', url,
            params=params, headers=headers, cookies=cookies,
            content=content, data=data, files=files, json=json,
            auth=auth, timeout=timeout,
            follow_redirects=follow_redirects, extensions=extensions,
        )

    async def put(
        self,
        url: str,
        *,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        content: RequestContent | None = None,
        data: RequestData | None = None,
        files: RequestFiles | None = None,
        json: Any | None = None,
        auth: AuthTypes | None = None,
        timeout: TimeoutTypes | None = None,
        follow_redirects: bool | None = None,
        extensions: RequestExtensions | None = None,
    ) -> httpx.Response:
        return await self.request(
            'PUT', url,
            params=params, headers=headers, cookies=cookies,
            content=content, data=data, files=files, json=json,
            auth=auth, timeout=timeout,
            follow_redirects=follow_redirects, extensions=extensions,
        )

    async def patch(
        self,
        url: str,
        *,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        content: RequestContent | None = None,
        data: RequestData | None = None,
        files: RequestFiles | None = None,
        json: Any | None = None,
        auth: AuthTypes | None = None,
        timeout: TimeoutTypes | None = None,
        follow_redirects: bool | None = None,
        extensions: RequestExtensions | None = None,
    ) -> httpx.Response:
        return await self.request(
            'PATCH', url,
            params=params, headers=headers, cookies=cookies,
            content=content, data=data, files=files, json=json,
            auth=auth, timeout=timeout,
            follow_redirects=follow_redirects, extensions=extensions,
        )

    async def delete(
        self,
        url: str,
        *,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        content: RequestContent | None = None,
        data: RequestData | None = None,
        files: RequestFiles | None = None,
        json: Any | None = None,
        auth: AuthTypes | None = None,
        timeout: TimeoutTypes | None = None,
        follow_redirects: bool | None = None,
        extensions: RequestExtensions | None = None,
    ) -> httpx.Response:
        return await self.request(
            'DELETE', url,
            params=params, headers=headers, cookies=cookies,
            content=content, data=data, files=files, json=json,
            auth=auth, timeout=timeout,
            follow_redirects=follow_redirects, extensions=extensions,
        )

    async def head(
        self,
        url: str,
        *,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        auth: AuthTypes | None = None,
        timeout: TimeoutTypes | None = None,
        follow_redirects: bool | None = None,
        extensions: RequestExtensions | None = None,
    ) -> httpx.Response:
        return await self.request(
            'HEAD', url,
            params=params, headers=headers, cookies=cookies,
            auth=auth, timeout=timeout,
            follow_redirects=follow_redirects, extensions=extensions,
        )

    # -- HTML parsing --

    async def get_html(
        self,
        url: str,
        *,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        auth: AuthTypes | None = None,
        timeout: TimeoutTypes | None = None,
        follow_redirects: bool | None = None,
        extensions: RequestExtensions | None = None,
    ) -> HtmlElement:
        """Fetch a URL and return a parsed lxml HtmlElement tree.

        Args:
            url: The target URL.
            params: Query parameters.
            headers: Request headers.
            cookies: Request cookies.
            auth: Authentication credentials or handler.
            timeout: Request timeout override.
            follow_redirects: Whether to follow HTTP redirects.
            extensions: Low-level httpx transport extensions.

        Returns:
            lxml.html.HtmlElement ready for XPath/CSS selectors.
        """
        response = await self.get(
            url,
            params=params, headers=headers, cookies=cookies,
            auth=auth, timeout=timeout,
            follow_redirects=follow_redirects, extensions=extensions,
        )
        response.raise_for_status()
        return lxml_html.fromstring(response.content)

    # -- Batch helpers --

    async def get_many(
        self,
        urls: list[str],
        *,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        auth: AuthTypes | None = None,
        timeout: TimeoutTypes | None = None,
        follow_redirects: bool | None = None,
        extensions: RequestExtensions | None = None,
    ) -> list[httpx.Response]:
        """Fetch multiple URLs concurrently, respecting rate limits.

        Args:
            urls: List of URLs to fetch.
            params: Query parameters applied to every request.
            headers: Headers applied to every request.
            cookies: Cookies applied to every request.
            auth: Authentication credentials or handler applied to every request.
            timeout: Request timeout override applied to every request.
            follow_redirects: Whether to follow HTTP redirects.
            extensions: Low-level httpx transport extensions.

        Returns:
            List of responses in the same order as the input URLs.
        """
        tasks = [
            self.get(
                url,
                params=params, headers=headers, cookies=cookies,
                auth=auth, timeout=timeout,
                follow_redirects=follow_redirects, extensions=extensions,
            )
            for url in urls
        ]
        return await asyncio.gather(*tasks)

    async def get_many_html(
        self,
        urls: list[str],
        *,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        auth: AuthTypes | None = None,
        timeout: TimeoutTypes | None = None,
        follow_redirects: bool | None = None,
        extensions: RequestExtensions | None = None,
    ) -> list[HtmlElement]:
        """Fetch multiple URLs concurrently and return parsed lxml trees."""
        tasks = [
            self.get_html(
                url,
                params=params, headers=headers, cookies=cookies,
                auth=auth, timeout=timeout,
                follow_redirects=follow_redirects, extensions=extensions,
            )
            for url in urls
        ]
        return await asyncio.gather(*tasks)

    @asynccontextmanager
    async def stream(
        self,
        method: str,
        url: str,
        *,
        params: QueryParamTypes | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        content: RequestContent | None = None,
        data: RequestData | None = None,
        files: RequestFiles | None = None,
        json: Any | None = None,
        auth: AuthTypes | None = None,
        timeout: TimeoutTypes | None = None,
        follow_redirects: bool | None = None,
        extensions: RequestExtensions | None = None,
    ) -> AsyncIterator[httpx.Response]:
        """Stream a response with rate limiting.

        Usage:
            async with client.stream("GET", url) as response:
                async for chunk in response.aiter_bytes():
                    ...
        """
        if self._client is None:
            await self.start()

        assert self._client is not None

        request_kwargs = self._build_request_kwargs(
            params=params,
            headers=headers,
            cookies=cookies,
            content=content,
            data=data,
            files=files,
            json=json,
            auth=auth,
            timeout=timeout,
            follow_redirects=follow_redirects,
            extensions=extensions,
        )

        ctx = await self._rate_limiter.acquire(url)
        async with ctx:
            async with self._client.stream(method, url, **request_kwargs) as response:
                yield response
