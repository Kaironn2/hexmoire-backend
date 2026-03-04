from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel


class HttpConfigOverrides(TypedDict, total=False):
    """Allowed overrides for HttpClientConfig.

    Use this as the type for ``http_config_overrides`` in bot base classes
    so that only valid config fields are accepted.
    """

    max_concurrent: int
    max_per_domain: int
    timeout: float
    retries: int
    retry_backoff: float
    retry_status_codes: set[int]
    default_headers: dict[str, str]
    proxy: str | None
    follow_redirects: bool
    verify_ssl: bool


class HttpClientConfig(BaseModel):
    """Configuration for the HTTP client.

    Attributes:
        max_concurrent: Maximum number of simultaneous requests globally.
        max_per_domain: Maximum number of simultaneous requests per domain.
        timeout: Default request timeout in seconds.
        retries: Number of retry attempts for failed requests.
        retry_backoff: Base delay (in seconds) between retries (exponential backoff).
        retry_status_codes: HTTP status codes that trigger a retry.
        default_headers: Headers sent with every request.
        proxy: Optional proxy URL (e.g. "http://user:pass@proxy:8080").
        follow_redirects: Whether to follow HTTP redirects.
        verify_ssl: Whether to verify SSL certificates.
    """

    max_concurrent: int = 20
    max_per_domain: int = 5
    timeout: float = 30.0
    retries: int = 3
    retry_backoff: float = 1.0
    retry_status_codes: set[int] = {429, 500, 502, 503, 504}
    default_headers: dict[str, str] = {}
    proxy: str | None = None
    follow_redirects: bool = True
    verify_ssl: bool = True

    def with_overrides(
        self,
        *,
        max_concurrent: int | None = None,
        max_per_domain: int | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        retry_backoff: float | None = None,
        retry_status_codes: set[int] | None = None,
        default_headers: dict[str, str] | None = None,
        proxy: str | None = None,
        follow_redirects: bool | None = None,
        verify_ssl: bool | None = None,
    ) -> HttpClientConfig:
        """Create a new config by merging this one with overrides.

        Only the provided fields are replaced; all others keep their current values.

        Usage:
            global_config = HttpClientConfig(max_concurrent=20)
            bot_config = global_config.with_overrides(max_concurrent=5, proxy="http://proxy:8080")
        """
        overrides = {
            k: v
            for k, v in {
                'max_concurrent': max_concurrent,
                'max_per_domain': max_per_domain,
                'timeout': timeout,
                'retries': retries,
                'retry_backoff': retry_backoff,
                'retry_status_codes': retry_status_codes,
                'default_headers': default_headers,
                'proxy': proxy,
                'follow_redirects': follow_redirects,
                'verify_ssl': verify_ssl,
            }.items()
            if v is not None
        }
        return self.model_copy(update=overrides)
