"""Shared request encoding and API error handling."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Optional, cast
from urllib.parse import quote

import httpx

from .types import V1Search

DEFAULT_BASE_URL = "https://api.quarryserp.com"


class QuarryError(Exception):
    """API or transport failure, including retry metadata and failed search data."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: Optional[int] = None,
        retryable: bool = False,
        search: Optional[V1Search] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.search = search
        self.retry_after = retry_after


def search_params(
    values: Dict[str, Any], *, cursor_only: bool = True
) -> Dict[str, Any]:
    """Convert Python options to API fields, omitting unspecified values."""
    names = {"resolve_links": "resolveLinks", "image_fallback": "imageFallback"}
    allowed = {"cursor", "mode", "cache", "thumbnails", "image_fallback"}
    return {
        names.get(key, key): value
        for key, value in values.items()
        if value is not None
        and (not cursor_only or values.get("cursor") is None or key in allowed)
    }


def query_params(values: Dict[str, Any]) -> Dict[str, str]:
    """Encode booleans with the API's lowercase representation."""
    return {
        k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in values.items()
    }


def search_path(id: str) -> str:
    """Escape a search ID as a single URL path component."""
    return "/v1/searches/" + quote(id, safe="")


def failed(search: V1Search, status_code: Optional[int] = None) -> QuarryError:
    """Turn a failed search envelope into an exception."""
    error = search.get("error", {})
    return QuarryError(
        error.get("code", "INTERNAL_ERROR"),
        error.get("message", "Search failed"),
        retryable=error.get("retryable", False),
        status_code=status_code,
        search=search,
    )


def retry_after(response: httpx.Response) -> Optional[float]:
    """Read Retry-After as seconds or an HTTP date."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            date = parsedate_to_datetime(raw)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def decode(response: httpx.Response, html: bool) -> Any:
    """Decode responses and normalize HTTP and failed-search errors."""
    if response.is_success and html:
        return response.text
    try:
        payload = response.json()
    except ValueError:
        payload = None
    is_failed = isinstance(payload, dict) and payload.get("status") == "failed"
    if response.is_success and not is_failed:
        if payload is None:
            raise QuarryError(
                "INTERNAL_ERROR",
                "Invalid JSON response",
                status_code=response.status_code,
            )
        return payload
    status = response.status_code
    defaults = {
        400: "INVALID_PARAMETER",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        429: "RATE_LIMITED",
        503: "BLOCKED_BY_CAPTCHA",
    }
    details = payload.get("error") if isinstance(payload, dict) else None
    details = details if isinstance(details, dict) else {}
    raise QuarryError(
        details.get("code", defaults.get(status, "INTERNAL_ERROR")),
        details.get(
            "message",
            response.text.strip()
            if payload is None and response.text.strip()
            else f"Request failed with HTTP status {status}",
        ),
        status_code=status,
        retryable=details.get("retryable", status >= 500),
        search=cast(V1Search, payload) if is_failed else None,
        retry_after=retry_after(response),
    )


class BaseQuarry:
    """Configuration and request helpers shared by both clients."""

    def _configure(
        self,
        api_key: Optional[str],
        base_url: str,
        timeout: float,
        max_retries: int,
        backoff: float,
        user_agent: Optional[str],
    ) -> None:
        key = api_key if api_key is not None else os.getenv("QUARRY_API_KEY")
        if not key or not key.strip():
            raise ValueError(
                "A Quarry API key is required: pass api_key or set QUARRY_API_KEY"
            )
        if max_retries < 0 or backoff < 0:
            raise ValueError("max_retries and backoff must be non-negative")
        self.api_key = key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.user_agent = user_agent or "quarryserp-python/0.1.0"

    def _url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return self.base_url + "/" + path.lstrip("/")

    def _headers(self, html: bool) -> Dict[str, str]:
        return {
            "Authorization": "Bearer " + self.api_key,
            "User-Agent": self.user_agent,
            "Accept": "text/html" if html else "application/json",
        }

    def _delay(self, error: QuarryError, attempt: int) -> float:
        delay = self.backoff * (attempt + 1)
        if error.status_code == 429 and error.retry_after is not None:
            delay = max(delay, error.retry_after)
        return delay
