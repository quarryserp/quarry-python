# Quarry Python SDK

[![PyPI version](https://img.shields.io/pypi/v/quarryserp)](https://pypi.org/project/quarryserp/)
[![CI](https://github.com/quarryserp/quarry-python/actions/workflows/ci.yml/badge.svg)](https://github.com/quarryserp/quarry-python/actions/workflows/ci.yml)

The official Python SDK for the [Quarry Google search results API](https://quarryserp.com).
Requires Python 3.9 or newer. Uses `httpx` for synchronous and asynchronous requests.

```sh
pip install quarryserp
export QUARRY_API_KEY="your-api-key"
```

```python
from quarryserp import Quarry

with Quarry() as client:
    search = client.search_and_wait("coffee", lang="en", country="us")
    for result in search.get("results", {}).get("organic", []):
        print(result["title"], result["url"])
```

Pass `api_key="..."` to override `QUARRY_API_KEY`. Unspecified search options use the
API defaults: type `web`, mode `sync`, cache enabled, resolve_links `organic`,
image_fallback `none`. All timeouts and backoff settings use **seconds**.

## Async

```python
import asyncio
from quarryserp import AsyncQuarry

async def main():
    async with AsyncQuarry() as client:
        images = await client.search_images("coffee", thumbnails=False)
        print(images)

asyncio.run(main())
```

`AsyncQuarry` has the same methods as `Quarry`; await each method, and use
`async for` with `paginate`. Use `close()` / `aclose()` or context managers to
release resources. If you supply an `http_client`, you own and close that client.

## Searches and polling

```python
with Quarry() as client:
    initial = client.submit("coffee", type="news")  # always mode=async
    search = client.wait_for(initial, timeout=180)
    saved = client.get(search["id"], thumbnails=False)
    raw_html = client.html(search["id"])
    usage = client.account()
```

`search()` can return `pending` even in sync mode. `wait_for(search_or_id)` follows
`pollUrl` and `retryAfterMs`. Its optional timeout limits the polling period;
the initial search or ID lookup has its own request timeout.
`search_and_wait()` combines search and polling. Vertical helpers
`search_news`, `search_videos`, `search_images`, `search_shopping`, and
`search_places` accept a query and search keyword options and return only the
corresponding result list (empty when absent).

Search options are `type`, `lang`, `country`, `cursor`, `mode`, `cache`,
`resolve_links`, `thumbnails`, and `image_fallback`. The SDK maps snake_case options
to the API's camelCase fields. Response dictionaries keep the original camelCase
keys. Exported TypedDicts, `GoogleLanguage` / `GoogleCountry` literals, and
`GOOGLE_LANGUAGES` / `GOOGLE_COUNTRIES` tuples provide editor support.

## Pagination

```python
with Quarry() as client:
    for page in client.paginate("coffee", max_pages=3, thumbnails=False):
        print(page.get("results", {}).get("organic", []))
```

Pages wait for completion. Later pages send only the next cursor and the thumbnail
option, matching the TypeScript client. `max_pages=0` makes no requests. When
calling `search(cursor=...)` directly, only cursor, mode, cache, thumbnails, and
image_fallback are sent; the cursor replaces the other search options.

## Errors and retries

```python
from quarryserp import Quarry, QuarryError

try:
    with Quarry(max_retries=2, backoff=0.5, timeout=120.0) as client:
        search = client.search_and_wait("coffee")
except QuarryError as error:
    print(error.code, error.message, error.status_code, error.retryable)
    print(error.retry_after)  # seconds from Retry-After, when present
    print(error.search)       # full failed search, when present
```

The default is no retries. Only retryable errors are retried, with linear delays
of `backoff * attempt`; HTTP 429 retries wait at least `Retry-After` seconds.
Connection and timeout errors use `NETWORK_ERROR`. Failed search envelopes raise
`QuarryError` even with HTTP 200. A polling timeout also raises `NETWORK_ERROR`.

Constructor options: `api_key=None`, `base_url="https://api.quarryserp.com"`,
`timeout=120.0`, `max_retries=0`, `backoff=0.5`, `user_agent=None`, and
`http_client=None`. The default User-Agent is `quarryserp-python/0.1.0`.

[Documentation](https://quarryserp.com/docs/python-http) ·
[Source](https://github.com/quarryserp/quarry-python) · MIT licensed.

## Development

```sh
uv run --with pytest --with pytest-asyncio pytest -q
uvx --with httpx mypy --strict src
uv build
```
