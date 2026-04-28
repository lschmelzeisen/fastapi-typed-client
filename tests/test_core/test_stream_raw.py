from collections.abc import AsyncIterable, Iterable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from ..client_tester import AsyncClientTester, ClientTester

_BYTES_CHUNKS = [b"hello ", b"world", b"!"]
_STR_CHUNKS = ["hello ", "world", "!"]


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/bytes-sync", response_class=StreamingResponse)
    def bytes_sync() -> Iterable[bytes]:
        yield from _BYTES_CHUNKS

    @app.get("/bytes-async", response_class=StreamingResponse)
    async def bytes_async() -> AsyncIterable[bytes]:
        for chunk in _BYTES_CHUNKS:
            yield chunk

    @app.get("/str-sync", response_class=StreamingResponse)
    def str_sync() -> Iterable[str]:
        yield from _STR_CHUNKS

    @app.get("/str-async", response_class=StreamingResponse)
    async def str_async() -> AsyncIterable[str]:
        for chunk in _STR_CHUNKS:
            yield chunk

    @app.get("/direct")
    def direct() -> StreamingResponse:
        async def gen() -> AsyncIterable[bytes]:
            for chunk in _BYTES_CHUNKS:
                yield chunk

        return StreamingResponse(gen())

    return app


def test_stream_raw(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import Iterator
        from typing import assert_type

        # Note: the endpoint's chunk boundaries cannot be observed in this test
        # because ASGITransport (used by `TestClient`) coalesces the streamed
        # body into a single buffer before handing it to httpx. So we can only
        # assert on the concatenated content, not the individual chunks.
        result_bytes_sync = client.bytes_sync()
        assert_type(result_bytes_sync.data, Iterator[bytes])  # type: ignore[client_tester_only]
        assert b"".join(result_bytes_sync.data) == b"hello world!"

        result_bytes_async = client.bytes_async()
        assert_type(result_bytes_async.data, Iterator[bytes])  # type: ignore[client_tester_only]
        assert b"".join(result_bytes_async.data) == b"hello world!"

        result_str_sync = client.str_sync()
        assert_type(result_str_sync.data, Iterator[str])  # type: ignore[client_tester_only]
        assert "".join(result_str_sync.data) == "hello world!"

        result_str_async = client.str_async()
        assert_type(result_str_async.data, Iterator[str])  # type: ignore[client_tester_only]
        assert "".join(result_str_async.data) == "hello world!"

        result_direct = client.direct()
        assert_type(result_direct.data, Iterator[bytes])  # type: ignore[client_tester_only]
        assert b"".join(result_direct.data) == b"hello world!"

    client_tester(app, client_test)


async def test_stream_raw_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import AsyncIterator
        from typing import assert_type

        async def collect_bytes(it: AsyncIterator[bytes]) -> bytes:
            buf = b""
            async for chunk in it:
                buf += chunk
            return buf

        async def collect_str(it: AsyncIterator[str]) -> str:
            buf = ""
            async for chunk in it:
                buf += chunk
            return buf

        # See note in the sync variant: ASGITransport coalesces streamed bodies,
        # so we can only assert on the concatenated content.
        result_bytes_sync = await client.bytes_sync()
        assert_type(result_bytes_sync.data, AsyncIterator[bytes])  # type: ignore[client_tester_only]
        assert await collect_bytes(result_bytes_sync.data) == b"hello world!"

        result_bytes_async = await client.bytes_async()
        assert_type(result_bytes_async.data, AsyncIterator[bytes])  # type: ignore[client_tester_only]
        assert await collect_bytes(result_bytes_async.data) == b"hello world!"

        result_str_sync = await client.str_sync()
        assert_type(result_str_sync.data, AsyncIterator[str])  # type: ignore[client_tester_only]
        assert await collect_str(result_str_sync.data) == "hello world!"

        result_str_async = await client.str_async()
        assert_type(result_str_async.data, AsyncIterator[str])  # type: ignore[client_tester_only]
        assert await collect_str(result_str_async.data) == "hello world!"

        result_direct = await client.direct()
        assert_type(result_direct.data, AsyncIterator[bytes])  # type: ignore[client_tester_only]
        assert await collect_bytes(result_direct.data) == b"hello world!"

    await async_client_tester(app, client_test)
