"""Behavioral contract tests; all requests use MockTransport."""

import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import get_args

import httpx
import pytest
from quarryserp import (
    GOOGLE_COUNTRIES,
    GOOGLE_LANGUAGES,
    AsyncQuarry,
    GoogleCountry,
    GoogleLanguage,
    Quarry,
    QuarryError,
)


def completed(**extra):
    return dict(
        id="s1",
        status="completed",
        query={"text": "coffee", "type": "web", "engine": "google"},
        meta={"cached": False, "createdAt": "2026-10-21"},
        results={"organic": [], "questions": [], "relatedQueries": []},
        **extra,
    )


def pending(**extra):
    return dict(
        id="s1",
        status="pending",
        query={"text": "coffee", "type": "web", "engine": "google"},
        meta={"cached": False, "createdAt": "2026-10-21"},
        **extra,
    )


def sync_client(handler, **options):
    return Quarry(
        "key",
        base_url="https://mock.test/",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        **options,
    )


def async_client(handler, **options):
    return AsyncQuarry(
        "key",
        base_url="https://mock.test/",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        **options,
    )


def test_search_parameters_headers_and_defaults():
    requests = []
    client = sync_client(
        lambda r: (requests.append(r), httpx.Response(200, json=completed()))[1]
    )
    assert client.base_url == "https://mock.test"
    client.search(
        "a+b & c",
        type="images",
        lang="pt-BR",
        country="us",
        mode="sync",
        cache=False,
        resolve_links="all",
        thumbnails=False,
        image_fallback="page",
    )
    request = requests[0]
    assert request.url.path == "/v1/search"
    assert dict(request.url.params) == dict(
        query="a+b & c",
        type="images",
        lang="pt-BR",
        country="us",
        mode="sync",
        cache="false",
        resolveLinks="all",
        thumbnails="false",
        imageFallback="page",
    )
    assert request.headers["Authorization"] == "Bearer key"
    assert request.headers["Accept"] == "application/json"
    assert request.headers["User-Agent"] == "quarryserp-python/0.1.0"
    client.search()
    assert not requests[1].url.params


def test_cursor_only_and_custom_user_agent():
    def handler(r):
        assert dict(r.url.params) == dict(
            cursor="opaque +/",
            mode="async",
            cache="true",
            thumbnails="false",
            imageFallback="page",
        )
        assert r.headers["User-Agent"] == "my-app"
        return httpx.Response(200, json=completed())

    sync_client(handler, user_agent="my-app").search(
        "ignored",
        cursor="opaque +/",
        type="news",
        lang="en",
        country="gb",
        resolve_links="none",
        mode="async",
        cache=True,
        thumbnails=False,
        image_fallback="page",
    )


def test_environment_and_missing_key(monkeypatch):
    monkeypatch.setenv("QUARRY_API_KEY", "env-key")
    with Quarry() as client:
        assert client.api_key == "env-key"
    with Quarry("explicit") as client:
        assert client.api_key == "explicit"
    monkeypatch.delenv("QUARRY_API_KEY")
    with pytest.raises(ValueError, match="QUARRY_API_KEY"):
        Quarry()
    with pytest.raises(ValueError):
        AsyncQuarry("")


def test_submit_body_and_get_encoding():
    requests = []
    client = sync_client(
        lambda r: (requests.append(r), httpx.Response(200, json=completed()))[1]
    )
    client.submit(
        "coffee",
        type="news",
        mode="sync",
        cache=False,
        resolve_links="none",
        thumbnails=False,
        image_fallback="page",
    )
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/v1/searches"
    assert json.loads(requests[0].content) == dict(
        query="coffee",
        type="news",
        mode="async",
        cache=False,
        resolveLinks="none",
        thumbnails=False,
        imageFallback="page",
    )
    assert requests[0].headers["content-type"] == "application/json"
    client.get("a/b ?", thumbnails=False)
    assert requests[1].url.raw_path == b"/v1/searches/a%2Fb%20%3F?thumbnails=false"
    client.get("s1", thumbnails=True)
    assert not requests[2].url.params


def test_wait_for_poll_url_and_delays(monkeypatch):
    sleeps, requests = [], []
    monkeypatch.setattr("quarryserp._client.time.sleep", sleeps.append)
    replies = iter(
        [
            pending(
                pollUrl="https://mock.test/v1/searches/alternate?thumbnails=false",
                retryAfterMs=25,
            ),
            completed(),
        ]
    )
    client = sync_client(
        lambda r: (requests.append(r), httpx.Response(200, json=next(replies)))[1]
    )
    result = client.wait_for(
        pending(pollUrl="/custom?thumbnails=false", retryAfterMs=12)
    )
    assert result["status"] == "completed"
    assert [str(r.url) for r in requests] == [
        "https://mock.test/custom?thumbnails=false",
        "https://mock.test/v1/searches/alternate?thumbnails=false",
    ]
    assert sleeps == [0.012, 0.025]
    assert client.wait_for(completed()) == completed()


def test_wait_for_id_and_search_and_wait(monkeypatch):
    monkeypatch.setattr("quarryserp._client.time.sleep", lambda _: None)
    requests = []
    responses = iter(
        [pending(retryAfterMs=0), completed(), pending(retryAfterMs=0), completed()]
    )
    client = sync_client(
        lambda r: (requests.append(r), httpx.Response(200, json=next(responses)))[1]
    )
    assert client.wait_for("s1")["status"] == "completed"
    assert client.search_and_wait("coffee")["status"] == "completed"
    assert [r.url.path for r in requests] == [
        "/v1/searches/s1",
        "/v1/searches/s1",
        "/v1/search",
        "/v1/searches/s1",
    ]


def test_wait_timeout_and_failed_input():
    client = sync_client(lambda _: pytest.fail("No request expected"))
    with pytest.raises(QuarryError, match="timed out") as exc:
        client.wait_for(pending(), timeout=0)
    assert exc.value.code == "NETWORK_ERROR"
    failed = dict(
        completed(),
        status="failed",
        error=dict(code="BLOCKED_BY_CAPTCHA", message="blocked", retryable=True),
    )
    with pytest.raises(QuarryError) as exc:
        client.wait_for(failed)
    assert exc.value.search == failed


def test_pagination_stops_and_preserves_thumbnails():
    requests = []
    replies = iter(
        [
            completed(pagination={"hasNext": True, "nextCursor": "next"}),
            completed(pagination={"hasNext": False}),
        ]
    )
    client = sync_client(
        lambda r: (requests.append(r), httpx.Response(200, json=next(replies)))[1]
    )
    assert (
        len(
            list(
                client.paginate(
                    "coffee", thumbnails=False, image_fallback="page", cache=False
                )
            )
        )
        == 2
    )
    assert dict(requests[1].url.params) == {"cursor": "next", "thumbnails": "false"}
    requests.clear()
    client = sync_client(
        lambda r: (
            requests.append(r),
            httpx.Response(
                200, json=completed(pagination={"hasNext": True, "nextCursor": "more"})
            ),
        )[1]
    )
    assert len(list(client.paginate("coffee", max_pages=1))) == 1
    assert len(requests) == 1
    assert list(client.paginate("coffee", max_pages=0)) == []
    assert len(requests) == 1


@pytest.mark.parametrize("vertical", ["news", "videos", "images", "shopping", "places"])
def test_helpers(vertical):
    requests = []
    page = completed()
    page["results"][vertical] = [{"rank": 1, "title": "Coffee"}]
    client = sync_client(
        lambda r: (requests.append(r), httpx.Response(200, json=page))[1]
    )
    assert (
        getattr(client, "search_" + vertical)("coffee", lang="en")
        == page["results"][vertical]
    )
    assert requests[0].url.params["type"] == vertical
    page["results"].pop(vertical)
    assert getattr(client, "search_" + vertical)("coffee") == []


def test_html_and_account():
    account = dict(
        keyId="k1",
        name="key",
        admin=False,
        plan=dict(monthlyQuota=100, ratePerMinute=5),
        usage=dict(month="2026-10", used=2, remaining=98),
    )

    def handler(r):
        if r.url.path.endswith("/html"):
            assert r.headers["Accept"] == "text/html"
            assert r.url.raw_path == b"/v1/searches/a%2Fb/html"
            return httpx.Response(200, text="<html>coffee</html>")
        assert r.url.path == "/v1/account"
        return httpx.Response(200, json=account)

    client = sync_client(handler)
    assert client.html("a/b") == "<html>coffee</html>"
    assert client.account() == account


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "UNAUTHORIZED"),
        (404, "NOT_FOUND"),
        (429, "RATE_LIMITED"),
        (500, "INTERNAL_ERROR"),
        (503, "BLOCKED_BY_CAPTCHA"),
    ],
)
def test_error_mapping(status, code):
    client = sync_client(
        lambda _: httpx.Response(status, text="oops", headers={"Retry-After": "3"})
    )
    with pytest.raises(QuarryError) as exc:
        client.search("coffee")
    assert exc.value.code == code
    assert exc.value.message == "oops"
    assert exc.value.status_code == status
    assert exc.value.retryable == (status >= 500)
    assert exc.value.retry_after == 3.0


@pytest.mark.parametrize("status", [200, 500, 503])
def test_failed_search_body(status):
    page = dict(
        completed(),
        status="failed",
        error=dict(code="BLOCKED_BY_CAPTCHA", message="try later", retryable=True),
    )
    client = sync_client(lambda _: httpx.Response(status, json=page))
    with pytest.raises(QuarryError) as exc:
        client.search("coffee")
    assert exc.value.search == page
    assert exc.value.retryable is True
    assert exc.value.code == "BLOCKED_BY_CAPTCHA"
    assert exc.value.status_code == status


def test_retries_retry_after_and_linear_backoff(monkeypatch):
    sleeps, calls = [], []
    monkeypatch.setattr("quarryserp._client.time.sleep", sleeps.append)
    replies = iter(
        [
            httpx.Response(
                429,
                json={
                    "error": dict(code="RATE_LIMITED", message="slow", retryable=True)
                },
                headers={"Retry-After": "3"},
            ),
            httpx.Response(
                500,
                json={
                    "error": dict(
                        code="INTERNAL_ERROR", message="again", retryable=True
                    )
                },
            ),
            httpx.Response(200, json=completed()),
        ]
    )
    client = sync_client(lambda r: (calls.append(r), next(replies))[1], max_retries=2)
    assert client.search("coffee")["status"] == "completed"
    assert len(calls) == 3
    assert sleeps == [3.0, 1.0]


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (401, "UNAUTHORIZED", False),
        (429, "QUOTA_EXCEEDED", False),
        (500, "INTERNAL_ERROR", False),
    ],
)
def test_no_retry_when_server_says_not_retryable(status, code, retryable):
    calls = []
    client = sync_client(
        lambda r: (
            calls.append(r),
            httpx.Response(
                status,
                json={"error": dict(code=code, message="stop", retryable=retryable)},
            ),
        )[1],
        max_retries=3,
    )
    with pytest.raises(QuarryError) as exc:
        client.search("coffee")
    assert exc.value.code == code
    assert len(calls) == 1


@pytest.mark.parametrize("exception", [httpx.ReadTimeout, httpx.ConnectError])
def test_network_error_and_retry(exception, monkeypatch):
    monkeypatch.setattr("quarryserp._client.time.sleep", lambda _: None)
    calls = []

    def handler(r):
        calls.append(r)
        raise exception("network down", request=r)

    client = sync_client(handler, max_retries=1)
    with pytest.raises(QuarryError) as exc:
        client.search("coffee")
    assert exc.value.code == "NETWORK_ERROR"
    assert exc.value.status_code is None
    assert exc.value.retryable
    assert len(calls) == 2


def test_retry_after_http_date_and_invalid_header():
    date = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=60))
    client = sync_client(
        lambda _: httpx.Response(
            429,
            headers={"Retry-After": date},
            json={"error": dict(code="RATE_LIMITED", message="slow", retryable=True)},
        )
    )
    with pytest.raises(QuarryError) as exc:
        client.account()
    assert 58 <= exc.value.retry_after <= 60
    for value in ["invalid", "-1"]:
        client = sync_client(
            lambda _: httpx.Response(429, headers={"Retry-After": value})
        )
        with pytest.raises(QuarryError) as exc:
            client.account()
        assert exc.value.retry_after == (None if value == "invalid" else 0)


def test_context_ownership_and_locales():
    with Quarry("x") as owned:
        assert not owned._client.is_closed
    assert owned._client.is_closed
    external = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=completed()))
    )
    with Quarry("x", http_client=external):
        pass
    assert not external.is_closed
    external.close()
    assert tuple(get_args(GoogleLanguage)) == GOOGLE_LANGUAGES
    assert tuple(get_args(GoogleCountry)) == GOOGLE_COUNTRIES
    assert "pt-BR" in GOOGLE_LANGUAGES and "us" in GOOGLE_COUNTRIES


async def test_async_main_paths(monkeypatch):
    requests, sleeps = [], []

    async def sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("quarryserp._async_client.asyncio.sleep", sleep)
    replies = iter(
        [
            pending(pollUrl="/poll?thumbnails=false", retryAfterMs=10),
            completed(),
            completed(),
            completed(pagination={"hasNext": True, "nextCursor": "next"}),
            completed(),
            completed(),
            completed(),
        ]
    )

    def handler(r):
        requests.append(r)
        if r.url.path.endswith("/html"):
            assert r.headers["Accept"] == "text/html"
            return httpx.Response(200, text="<html/>")
        if r.url.path == "/v1/account":
            return httpx.Response(200, json={"keyId": "k1"})
        return httpx.Response(200, json=next(replies))

    client = async_client(handler)
    async with client:
        assert (await client.search_and_wait("coffee", thumbnails=False))[
            "status"
        ] == "completed"
        assert str(requests[1].url) == "https://mock.test/poll?thumbnails=false"
        assert sleeps == [0.01]
        await client.submit("coffee", resolve_links="all", mode="sync")
        assert json.loads(requests[2].content) == dict(
            query="coffee", mode="async", resolveLinks="all"
        )
        pages = [
            p async for p in client.paginate("coffee", thumbnails=False, max_pages=3)
        ]
        assert len(pages) == 2
        assert dict(requests[4].url.params) == dict(cursor="next", thumbnails="false")
        await client.get("s1", thumbnails=False)
        assert requests[-1].url.params["thumbnails"] == "false"
        assert await client.search_news("coffee") == []
        assert await client.html("s1") == "<html/>"
        assert await client.account() == {"keyId": "k1"}
    await client._client.aclose()
    async with AsyncQuarry("x") as owned:
        assert not owned._client.is_closed
    assert owned._client.is_closed


async def test_async_cursor_errors_retries_and_timeout(monkeypatch):
    sleeps, requests = [], []

    async def sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("quarryserp._async_client.asyncio.sleep", sleep)
    replies = iter(
        [
            httpx.Response(
                429,
                headers={"Retry-After": "2"},
                json={
                    "error": dict(code="RATE_LIMITED", message="slow", retryable=True)
                },
            ),
            httpx.Response(200, json=completed()),
        ]
    )
    client = async_client(
        lambda r: (requests.append(r), next(replies))[1], max_retries=1
    )
    await client.search("ignored", type="news", cursor="c", thumbnails=False)
    assert dict(requests[0].url.params) == dict(cursor="c", thumbnails="false")
    assert sleeps == [2.0]

    def timeout(r):
        raise httpx.ReadTimeout("timeout", request=r)

    client = async_client(timeout)
    with pytest.raises(QuarryError) as exc:
        await client.search("coffee")
    assert exc.value.code == "NETWORK_ERROR"
    with pytest.raises(QuarryError):
        await client.wait_for(pending(), timeout=0)
    failed = dict(
        completed(),
        status="failed",
        error=dict(code="INTERNAL_ERROR", message="failed", retryable=False),
    )
    with pytest.raises(QuarryError) as exc:
        await client.wait_for(failed)
    assert exc.value.search == failed
    await client._client.aclose()


def test_polling_deadline_limits_retries(monkeypatch):
    now, requests, sleeps = [0.0], [], []
    monkeypatch.setattr("quarryserp._client._clock.monotonic", lambda: now[0])

    def sleep(delay):
        sleeps.append(delay)
        now[0] += delay

    monkeypatch.setattr("quarryserp._client.time.sleep", sleep)
    client = sync_client(
        lambda r: (requests.append(r), httpx.Response(500))[1],
        max_retries=10,
        backoff=2,
    )
    with pytest.raises(QuarryError, match="timed out"):
        client.wait_for(pending(retryAfterMs=100), timeout=1)
    assert len(requests) == 1
    assert sleeps == [0.1, 0.9]
    assert requests[0].extensions["timeout"]["read"] == pytest.approx(0.9)


def test_default_retries_are_disabled():
    calls = []
    client = sync_client(lambda r: (calls.append(r), httpx.Response(500))[1])
    with pytest.raises(QuarryError):
        client.search("coffee")
    assert len(calls) == 1


def test_submit_cursor_preserves_body_fields_like_typescript():
    def handler(r):
        assert json.loads(r.content) == dict(
            query="coffee", cursor="c", type="news", mode="async"
        )
        return httpx.Response(200, json=completed())

    sync_client(handler).submit("coffee", cursor="c", type="news")


def test_invalid_json_error():
    client = sync_client(lambda _: httpx.Response(200, text="invalid"))
    with pytest.raises(QuarryError, match="Invalid JSON"):
        client.search("coffee")


@pytest.mark.parametrize("vertical", ["news", "videos", "images", "shopping", "places"])
async def test_async_helpers(vertical):
    requests = []
    page = completed()
    page["results"][vertical] = [{"rank": 1, "title": "Coffee"}]
    client = async_client(
        lambda r: (requests.append(r), httpx.Response(200, json=page))[1]
    )
    assert (
        await getattr(client, "search_" + vertical)("coffee", thumbnails=False)
        == page["results"][vertical]
    )
    assert requests[0].url.params["type"] == vertical
    page["results"].pop(vertical)
    assert await getattr(client, "search_" + vertical)("coffee") == []
    await client._client.aclose()


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (401, "UNAUTHORIZED", False),
        (404, "NOT_FOUND", False),
        (429, "RATE_LIMITED", True),
        (500, "INTERNAL_ERROR", True),
    ],
)
async def test_async_error_mapping(status, code, retryable):
    client = async_client(
        lambda _: httpx.Response(
            status,
            headers={"Retry-After": "4"},
            json={"error": dict(code=code, message="failed", retryable=retryable)},
        )
    )
    with pytest.raises(QuarryError) as exc:
        await client.search("coffee")
    assert exc.value.code == code
    assert exc.value.retryable == retryable
    assert exc.value.status_code == status
    assert exc.value.retry_after == 4
    await client._client.aclose()


async def test_async_failed_http_body_no_retry_and_pagination_limit():
    requests = []
    page = dict(
        completed(),
        status="failed",
        error=dict(code="INTERNAL_ERROR", message="failed", retryable=False),
    )
    client = async_client(
        lambda r: (requests.append(r), httpx.Response(200, json=page))[1], max_retries=3
    )
    with pytest.raises(QuarryError) as exc:
        await client.search("coffee")
    assert exc.value.search == page
    assert len(requests) == 1
    assert [p async for p in client.paginate("coffee", max_pages=0)] == []
    assert len(requests) == 1
    page.clear()
    page.update(completed(pagination={"hasNext": True, "nextCursor": "next"}))
    assert len([p async for p in client.paginate("coffee", max_pages=1)]) == 1
    await client._client.aclose()


async def test_async_wait_id_and_deadline_limits_retries(monkeypatch):
    now, sleeps, requests = [0.0], [], []
    monkeypatch.setattr("quarryserp._async_client._clock.monotonic", lambda: now[0])

    async def sleep(delay):
        sleeps.append(delay)
        now[0] += delay

    monkeypatch.setattr("quarryserp._async_client.asyncio.sleep", sleep)
    responses = iter([pending(retryAfterMs=100), completed()])
    client = async_client(
        lambda r: (requests.append(r), httpx.Response(200, json=next(responses)))[1]
    )
    assert (await client.wait_for("s1"))["status"] == "completed"
    await client._client.aclose()
    requests.clear()
    sleeps.clear()
    now[0] = 0
    client = async_client(
        lambda r: (requests.append(r), httpx.Response(500))[1],
        max_retries=10,
        backoff=2,
    )
    with pytest.raises(QuarryError, match="timed out"):
        await client.wait_for(pending(retryAfterMs=100), timeout=1)
    assert len(requests) == 1
    assert sleeps == [0.1, 0.9]
    await client._client.aclose()
