from collections.abc import AsyncIterable, Iterable
from typing import Any

import pytest
from fastapi import FastAPI

from ..client_tester import AsyncClientTester, ClientTester
from ..shared import TEXT_AND_NUM_DATA, TextAndNum


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/foo-sync")
    def foo_sync() -> Iterable[TextAndNum]:
        yield from TEXT_AND_NUM_DATA

    @app.get("/foo-async")
    async def foo_async() -> AsyncIterable[TextAndNum]:
        for item in TEXT_AND_NUM_DATA:
            yield item

    return app


def test_stream_json_lines(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import Iterator
        from typing import assert_type

        from ..shared import TEXT_AND_NUM_DATA, TextAndNum

        result_sync = client.foo_sync()
        assert_type(result_sync.data, Iterator[TextAndNum])  # type: ignore[client_tester_only]
        for item, expected_item in zip(
            result_sync.data, TEXT_AND_NUM_DATA, strict=True
        ):
            assert_type(item, TextAndNum)  # type: ignore[client_tester_only]
            assert item == expected_item

        result_async = client.foo_async()
        assert_type(result_async.data, Iterator[TextAndNum])  # type: ignore[client_tester_only]
        for item, expected_item in zip(
            result_async.data, TEXT_AND_NUM_DATA, strict=True
        ):
            assert_type(item, TextAndNum)  # type: ignore[client_tester_only]
            assert item == expected_item

    client_tester(app, client_test)


async def test_stream_json_lines_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import AsyncIterator
        from typing import assert_type

        from ..shared import TEXT_AND_NUM_DATA, TextAndNum

        result_sync = await client.foo_sync()
        assert_type(result_sync.data, AsyncIterator[TextAndNum])  # type: ignore[client_tester_only]
        expected_iter = iter(TEXT_AND_NUM_DATA)
        async for item in result_sync.data:
            expected = next(expected_iter)
            assert_type(item, TextAndNum)  # type: ignore[client_tester_only]
            assert item == expected
        assert next(expected_iter, None) is None

        result_async = await client.foo_async()
        assert_type(result_async.data, AsyncIterator[TextAndNum])  # type: ignore[client_tester_only]
        expected_iter = iter(TEXT_AND_NUM_DATA)
        async for item in result_async.data:
            expected = next(expected_iter)
            assert_type(item, TextAndNum)  # type: ignore[client_tester_only]
            assert item == expected
        assert next(expected_iter, None) is None

    await async_client_tester(app, client_test)
