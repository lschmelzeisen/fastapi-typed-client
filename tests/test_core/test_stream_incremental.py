"""Streaming-endpoint tests run against a real loopback uvicorn server.

The sibling `test_stream_*.py` files use `httpx2.ASGITransport`, which
coalesces the response body — a client that buffered the whole body would
pass them. These tests use a real socket where chunk boundaries are real.

Each endpoint emits two items, awaits a server-held `Event`, then (after
`/release` sets it) emits a third item and closes. Each test reads two
items, verifies the stream blocks, hits `/release`, reads the third item,
and asserts the stream closes naturally. A buffering client would deadlock
at the first read — the body has no end-of-stream until `/release` fires.
"""

from collections.abc import AsyncIterable, AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import uvicorn
from anyio import Event, create_task_group, sleep
from anyio.from_thread import start_blocking_portal
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.sse import EventSourceResponse
from httpx2 import AsyncClient, Client

from ..client_tester import AsyncClientTester, ClientTester
from ..shared import TextAndNum

_TICK_INTERVAL = 0.01
_CLIENT_TIMEOUT = 0.5


@pytest.fixture
def app() -> FastAPI:  # noqa: C901 — four similar endpoints + shared event helper
    app = FastAPI()
    # `anyio.Event()` needs a running event loop to construct; this fixture is sync, so
    # defer instantiation to the first request handler.
    event: Event | None = None

    def get_event() -> Event:
        nonlocal event
        if event is None:
            event = Event()
        return event

    @app.get("/sse", response_class=EventSourceResponse)
    async def sse() -> AsyncIterable[TextAndNum]:
        event = get_event()
        for i in range(2):
            yield TextAndNum(text="tick", num=i)
            await sleep(_TICK_INTERVAL)
        await event.wait()
        yield TextAndNum(text="tick", num=2)

    @app.get("/json-lines")
    async def json_lines() -> AsyncIterable[TextAndNum]:
        event = get_event()
        for i in range(2):
            yield TextAndNum(text="tick", num=i)
            await sleep(_TICK_INTERVAL)
        await event.wait()
        yield TextAndNum(text="tick", num=2)

    @app.get("/raw-bytes", response_class=StreamingResponse)
    async def raw_bytes() -> AsyncIterable[bytes]:
        event = get_event()
        for i in range(2):
            yield f"tick-{i}\n".encode()
            await sleep(_TICK_INTERVAL)
        await event.wait()
        yield b"tick-2\n"

    @app.get("/raw-str", response_class=StreamingResponse)
    async def raw_str() -> AsyncIterable[str]:
        event = get_event()
        for i in range(2):
            yield f"tick-{i}\n"
            await sleep(_TICK_INTERVAL)
        await event.wait()
        yield "tick-2\n"

    @app.post("/release")
    async def release() -> None:
        get_event().set()

    return app


@asynccontextmanager
async def _serve_uvicorn(app: FastAPI) -> AsyncIterator[str]:
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,  # Random free port.
        lifespan="off",
        ws="none",  # We don't use websockets.
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    async with create_task_group() as tg:
        tg.start_soon(server.serve)
        # uvicorn doesn't surface a startup event to `await`, so poll instead.
        while not server.started:  # noqa: ASYNC110
            await sleep(_TICK_INTERVAL)
        host, port = server.servers[0].sockets[0].getsockname()[:2]
        yield f"http://{host}:{port}"
        server.should_exit = True


@pytest.fixture
def app_client(app: FastAPI) -> Iterator[Client]:
    with (
        start_blocking_portal() as portal,
        portal.wrap_async_context_manager(_serve_uvicorn(app)) as url,
        Client(base_url=url, timeout=_CLIENT_TIMEOUT) as client,
    ):
        yield client


@pytest.fixture
async def async_app_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with (
        _serve_uvicorn(app) as url,
        AsyncClient(base_url=url, timeout=_CLIENT_TIMEOUT) as client,
    ):
        yield client


def test_stream_sse_real_socket(
    app: FastAPI, app_client: Client, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        import time
        from concurrent.futures import ThreadPoolExecutor

        from ..shared import TextAndNum

        stream = client.sse().data
        first = next(stream)
        second = next(stream)
        assert first.data == TextAndNum(text="tick", num=0)
        assert second.data == TextAndNum(text="tick", num=1)

        rest: list = []

        def drain() -> None:
            for item in stream:
                rest.append(item)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(drain)
            time.sleep(0.1)
            assert not rest, "stream should block while server awaits release"
            client.release()
            future.result(timeout=0.1)

        assert len(rest) == 1
        assert rest[0].data == TextAndNum(text="tick", num=2)

    client_tester(app, client_test, httpx_client=app_client)


def test_stream_json_lines_real_socket(
    app: FastAPI, app_client: Client, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        import time
        from concurrent.futures import ThreadPoolExecutor

        from ..shared import TextAndNum

        stream = client.json_lines().data
        first = next(stream)
        second = next(stream)
        assert first == TextAndNum(text="tick", num=0)
        assert second == TextAndNum(text="tick", num=1)

        rest: list = []

        def drain() -> None:
            for item in stream:
                rest.append(item)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(drain)
            time.sleep(0.1)
            assert not rest, "stream should block while server awaits release"
            client.release()
            future.result(timeout=0.1)

        assert rest == [TextAndNum(text="tick", num=2)]

    client_tester(app, client_test, httpx_client=app_client)


def test_stream_raw_bytes_real_socket(
    app: FastAPI, app_client: Client, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        import time
        from concurrent.futures import ThreadPoolExecutor

        stream = client.raw_bytes().data
        buf = b""
        for chunk in stream:
            buf += chunk
            if buf.count(b"\n") >= 2:
                break
        assert buf == b"tick-0\ntick-1\n"

        rest: list = []

        def drain() -> None:
            for chunk in stream:
                rest.append(chunk)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(drain)
            time.sleep(0.1)
            assert not rest, "stream should block while server awaits release"
            client.release()
            future.result(timeout=0.1)

        assert b"".join(rest) == b"tick-2\n"

    client_tester(app, client_test, httpx_client=app_client)


def test_stream_raw_str_real_socket(
    app: FastAPI, app_client: Client, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        import time
        from concurrent.futures import ThreadPoolExecutor

        stream = client.raw_str().data
        buf = ""
        for chunk in stream:
            buf += chunk
            if buf.count("\n") >= 2:
                break
        assert buf == "tick-0\ntick-1\n"

        rest: list = []

        def drain() -> None:
            for chunk in stream:
                rest.append(chunk)

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(drain)
            time.sleep(0.1)
            assert not rest, "stream should block while server awaits release"
            client.release()
            future.result(timeout=0.1)

        assert "".join(rest) == "tick-2\n"

    client_tester(app, client_test, httpx_client=app_client)


async def test_stream_sse_real_socket_async(
    app: FastAPI,
    async_app_client: AsyncClient,
    async_client_tester: AsyncClientTester,
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from anyio import create_task_group, fail_after, sleep

        from ..shared import TextAndNum

        result = await client.sse()
        stream = result.data
        first = await anext(stream)
        second = await anext(stream)
        assert first.data == TextAndNum(text="tick", num=0)
        assert second.data == TextAndNum(text="tick", num=1)

        rest: list = []

        async def drain() -> None:
            async for item in stream:
                rest.append(item)

        with fail_after(0.5):
            async with create_task_group() as tg:
                tg.start_soon(drain)
                await sleep(0.1)
                assert not rest, "stream should block while server awaits release"
                await client.release()

        assert len(rest) == 1
        assert rest[0].data == TextAndNum(text="tick", num=2)

    await async_client_tester(app, client_test, httpx_client=async_app_client)


async def test_stream_json_lines_real_socket_async(
    app: FastAPI,
    async_app_client: AsyncClient,
    async_client_tester: AsyncClientTester,
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from anyio import create_task_group, fail_after, sleep

        from ..shared import TextAndNum

        result = await client.json_lines()
        stream = result.data
        first = await anext(stream)
        second = await anext(stream)
        assert first == TextAndNum(text="tick", num=0)
        assert second == TextAndNum(text="tick", num=1)

        rest: list = []

        async def drain() -> None:
            async for item in stream:
                rest.append(item)

        with fail_after(0.5):
            async with create_task_group() as tg:
                tg.start_soon(drain)
                await sleep(0.1)
                assert not rest, "stream should block while server awaits release"
                await client.release()

        assert rest == [TextAndNum(text="tick", num=2)]

    await async_client_tester(app, client_test, httpx_client=async_app_client)


async def test_stream_raw_bytes_real_socket_async(
    app: FastAPI,
    async_app_client: AsyncClient,
    async_client_tester: AsyncClientTester,
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from anyio import create_task_group, fail_after, sleep

        result = await client.raw_bytes()
        stream = result.data
        buf = b""
        async for chunk in stream:
            buf += chunk
            if buf.count(b"\n") >= 2:
                break
        assert buf == b"tick-0\ntick-1\n"

        rest: list = []

        async def drain() -> None:
            async for chunk in stream:
                rest.append(chunk)

        with fail_after(0.5):
            async with create_task_group() as tg:
                tg.start_soon(drain)
                await sleep(0.1)
                assert not rest, "stream should block while server awaits release"
                await client.release()

        assert b"".join(rest) == b"tick-2\n"

    await async_client_tester(app, client_test, httpx_client=async_app_client)


async def test_stream_raw_str_real_socket_async(
    app: FastAPI,
    async_app_client: AsyncClient,
    async_client_tester: AsyncClientTester,
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from anyio import create_task_group, fail_after, sleep

        result = await client.raw_str()
        stream = result.data
        buf = ""
        async for chunk in stream:
            buf += chunk
            if buf.count("\n") >= 2:
                break
        assert buf == "tick-0\ntick-1\n"

        rest: list = []

        async def drain() -> None:
            async for chunk in stream:
                rest.append(chunk)

        with fail_after(0.5):
            async with create_task_group() as tg:
                tg.start_soon(drain)
                await sleep(0.1)
                assert not rest, "stream should block while server awaits release"
                await client.release()

        assert "".join(rest) == "tick-2\n"

    await async_client_tester(app, client_test, httpx_client=async_app_client)
