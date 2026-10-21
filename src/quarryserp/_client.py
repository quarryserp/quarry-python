"""Official synchronous Quarry client."""

from __future__ import annotations

import time
import time as _clock
from types import TracebackType
from typing import Any, Dict, Iterator, List, Optional, Type, Union, cast

import httpx

from ._base import (
    DEFAULT_BASE_URL,
    BaseQuarry,
    QuarryError,
    decode,
    failed,
    query_params,
    search_params,
    search_path,
)
from .locales import GoogleCountry, GoogleLanguage
from .types import (
    ImageFallback,
    ResolveLinks,
    SearchMode,
    SearchType,
    V1Account,
    V1Image,
    V1News,
    V1Place,
    V1Product,
    V1Search,
    V1Video,
)


class Quarry(BaseQuarry):
    """Quarry v1 client. Use a context manager to release owned HTTP resources.

    A supplied http_client remains owned by the caller. Timeouts and backoff
    are in seconds; max_retries defaults to zero.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 120.0,
        max_retries: int = 0,
        backoff: float = 0.5,
        user_agent: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._configure(api_key, base_url, timeout, max_retries, backoff, user_agent)
        self._owns_client = http_client is None
        self._client = http_client if http_client is not None else httpx.Client()

    def close(self) -> None:
        """Close the HTTP client created by this instance."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Quarry:
        """Enter a managed client scope."""
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Release owned resources when leaving the scope."""
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
        html: bool = False,
        deadline: Optional[float] = None,
    ) -> Any:
        for attempt in range(self.max_retries + 1):
            remaining = None if deadline is None else deadline - _clock.monotonic()
            if remaining is not None and remaining <= 0:
                raise QuarryError("NETWORK_ERROR", "wait_for timed out", retryable=True)
            try:
                try:
                    response = self._client.request(
                        method,
                        self._url(path),
                        params=params,
                        json=body,
                        headers=self._headers(html),
                        timeout=self.timeout
                        if remaining is None
                        else min(self.timeout, remaining),
                    )
                except httpx.RequestError as cause:
                    raise QuarryError(
                        "NETWORK_ERROR",
                        str(cause) or "Network request failed",
                        retryable=True,
                    ) from cause
                return decode(response, html)
            except QuarryError as error:
                if not error.retryable or attempt >= self.max_retries:
                    raise
                delay = self._delay(error, attempt)
                if deadline is not None:
                    delay = min(delay, max(0.0, deadline - _clock.monotonic()))
                time.sleep(delay)
        raise AssertionError("Unreachable retry state")

    def search(
        self,
        query: Optional[str] = None,
        *,
        type: Optional[SearchType] = None,
        lang: Optional[GoogleLanguage] = None,
        country: Optional[GoogleCountry] = None,
        cursor: Optional[str] = None,
        mode: Optional[SearchMode] = None,
        cache: Optional[bool] = None,
        resolve_links: Optional[ResolveLinks] = None,
        thumbnails: Optional[bool] = None,
        image_fallback: Optional[ImageFallback] = None,
    ) -> V1Search:
        """Run a search; sync mode can still return pending at the server deadline.

        A cursor replaces query, type, lang, country and resolve_links.
        Unspecified options use the API defaults.
        """
        params = search_params(
            dict(
                query=query,
                type=type,
                lang=lang,
                country=country,
                cursor=cursor,
                mode=mode,
                cache=cache,
                resolve_links=resolve_links,
                thumbnails=thumbnails,
                image_fallback=image_fallback,
            )
        )
        return cast(
            V1Search, self._request("GET", "/v1/search", params=query_params(params))
        )

    def submit(
        self,
        query: Optional[str] = None,
        *,
        type: Optional[SearchType] = None,
        lang: Optional[GoogleLanguage] = None,
        country: Optional[GoogleCountry] = None,
        cursor: Optional[str] = None,
        mode: Optional[SearchMode] = None,
        cache: Optional[bool] = None,
        resolve_links: Optional[ResolveLinks] = None,
        thumbnails: Optional[bool] = None,
        image_fallback: Optional[ImageFallback] = None,
    ) -> V1Search:
        """Submit a search with mode=async and return its initial status."""
        body = search_params(
            dict(
                query=query,
                type=type,
                lang=lang,
                country=country,
                cursor=cursor,
                mode=mode,
                cache=cache,
                resolve_links=resolve_links,
                thumbnails=thumbnails,
                image_fallback=image_fallback,
            ),
            cursor_only=False,
        )
        body["mode"] = "async"
        return cast(V1Search, self._request("POST", "/v1/searches", body=body))

    def get(self, id: str, *, thumbnails: Optional[bool] = None) -> V1Search:
        """Fetch an archived search or poll its status by ID."""
        params = {"thumbnails": "false"} if thumbnails is False else None
        return cast(V1Search, self._request("GET", search_path(id), params=params))

    def wait_for(
        self, search_or_id: Union[str, V1Search], *, timeout: Optional[float] = None
    ) -> V1Search:
        """Poll pollUrl using retryAfterMs until completion; timeout is seconds."""
        current = (
            self.get(search_or_id) if isinstance(search_or_id, str) else search_or_id
        )
        deadline = None if timeout is None else _clock.monotonic() + timeout
        while current["status"] == "pending":
            remaining = None if deadline is None else deadline - _clock.monotonic()
            if remaining is not None and remaining <= 0:
                raise QuarryError("NETWORK_ERROR", "wait_for timed out", retryable=True)
            delay = max(0.0, current.get("retryAfterMs", 1000) / 1000)
            time.sleep(delay if remaining is None else min(delay, max(0.0, remaining)))
            remaining = None if deadline is None else deadline - _clock.monotonic()
            if remaining is not None and remaining <= 0:
                raise QuarryError("NETWORK_ERROR", "wait_for timed out", retryable=True)
            path = current.get("pollUrl") or search_path(current["id"])
            current = self._request(
                "GET",
                path,
                deadline=deadline,
            )
        if current["status"] == "failed":
            raise failed(current)
        return current

    def search_and_wait(
        self,
        query: Optional[str] = None,
        *,
        type: Optional[SearchType] = None,
        lang: Optional[GoogleLanguage] = None,
        country: Optional[GoogleCountry] = None,
        cursor: Optional[str] = None,
        mode: Optional[SearchMode] = None,
        cache: Optional[bool] = None,
        resolve_links: Optional[ResolveLinks] = None,
        thumbnails: Optional[bool] = None,
        image_fallback: Optional[ImageFallback] = None,
        timeout: Optional[float] = None,
    ) -> V1Search:
        """Run a search and continue polling when it returns pending."""
        result = self.search(
            query,
            type=type,
            lang=lang,
            country=country,
            cursor=cursor,
            mode=mode,
            cache=cache,
            resolve_links=resolve_links,
            thumbnails=thumbnails,
            image_fallback=image_fallback,
        )
        return self.wait_for(result, timeout=timeout)

    def paginate(
        self,
        query: Optional[str] = None,
        *,
        type: Optional[SearchType] = None,
        lang: Optional[GoogleLanguage] = None,
        country: Optional[GoogleCountry] = None,
        cursor: Optional[str] = None,
        mode: Optional[SearchMode] = None,
        cache: Optional[bool] = None,
        resolve_links: Optional[ResolveLinks] = None,
        thumbnails: Optional[bool] = None,
        image_fallback: Optional[ImageFallback] = None,
        max_pages: Optional[int] = None,
    ) -> Iterator[V1Search]:
        """Yield completed pages, following nextCursor; later pages retain thumbnails."""
        params: Dict[str, Any] = dict(
            query=query,
            type=type,
            lang=lang,
            country=country,
            cursor=cursor,
            mode=mode,
            cache=cache,
            resolve_links=resolve_links,
            thumbnails=thumbnails,
            image_fallback=image_fallback,
        )
        count = 0
        while max_pages is None or count < max_pages:
            page = self.search_and_wait(**params)
            yield page
            count += 1
            cursor = page.get("pagination", {}).get("nextCursor")
            if not cursor:
                break
            params = {"cursor": cursor, "thumbnails": thumbnails}

    def search_news(self, query: str, **params: Any) -> List[V1News]:
        """Return the news result list, waiting for completion when needed."""
        result = self.search_and_wait(query, type="news", **params)
        return result.get("results", {}).get("news", [])

    def search_videos(self, query: str, **params: Any) -> List[V1Video]:
        """Return the videos result list, waiting for completion when needed."""
        result = self.search_and_wait(query, type="videos", **params)
        return result.get("results", {}).get("videos", [])

    def search_images(self, query: str, **params: Any) -> List[V1Image]:
        """Return the images result list, waiting for completion when needed."""
        result = self.search_and_wait(query, type="images", **params)
        return result.get("results", {}).get("images", [])

    def search_shopping(self, query: str, **params: Any) -> List[V1Product]:
        """Return the shopping result list, waiting for completion when needed."""
        result = self.search_and_wait(query, type="shopping", **params)
        return result.get("results", {}).get("shopping", [])

    def search_places(self, query: str, **params: Any) -> List[V1Place]:
        """Return the places result list, waiting for completion when needed."""
        result = self.search_and_wait(query, type="places", **params)
        return result.get("results", {}).get("places", [])

    def html(self, id: str) -> str:
        """Retrieve archived raw HTML for a search."""
        return cast(str, self._request("GET", search_path(id) + "/html", html=True))

    def account(self) -> V1Account:
        """Return the account plan and current UTC month's usage."""
        return cast(V1Account, self._request("GET", "/v1/account"))
