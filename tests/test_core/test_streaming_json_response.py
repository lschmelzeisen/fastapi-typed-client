from collections.abc import AsyncIterable, AsyncIterator, Sequence
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse

from ..client_tester import AsyncClientTester, ClientTester
from ..shared import TEXT_AND_NUM_DATA, TextAndNum


# This class is not something that is necessarily suited for production use cases.
# Instead, it is the minimal code to the streaming JSON functionality of this package.
class JSONStreamingResponse(StreamingResponse, JSONResponse):
    def __init__(self, content: AsyncIterable[Any]) -> None:
        async def content_iter() -> AsyncIterable[bytes]:
            async for item in content:
                yield self.render(jsonable_encoder(item)) + b"\n"

        super().__init__(content_iter())


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    async def stream() -> AsyncIterator[TextAndNum]:
        for item in TEXT_AND_NUM_DATA:
            yield item

    @app.get("/foo", response_model=TextAndNum)
    def foo() -> JSONStreamingResponse:
        return JSONStreamingResponse(stream())

    @app.get("/foo-seq", response_model=Sequence[TextAndNum])
    def foo_seq() -> JSONStreamingResponse:
        return JSONStreamingResponse(stream())

    return app


def test_json_streaming_response(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import Iterator
        from typing import assert_type

        from ..shared import TEXT_AND_NUM_DATA, TextAndNum

        result1 = client.foo()
        assert_type(result1.data, Iterator[TextAndNum])  # type: ignore[client_tester_only]
        for item, expected_item in zip(result1.data, TEXT_AND_NUM_DATA, strict=True):
            assert item == expected_item

        result2 = client.foo_seq()
        assert_type(result2.data, Iterator[TextAndNum])  # type: ignore[client_tester_only]
        for item, expected_item in zip(result2.data, TEXT_AND_NUM_DATA, strict=True):
            assert_type(item, TextAndNum)  # type: ignore[client_tester_only]
            assert item == expected_item

    client_tester(app, client_test)


async def test_json_streaming_response_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import AsyncIterator
        from typing import assert_type

        from ..shared import TEXT_AND_NUM_DATA, TextAndNum

        result1 = await client.foo()
        assert_type(result1.data, AsyncIterator[TextAndNum])  # type: ignore[client_tester_only]
        expected_items_iter = iter(TEXT_AND_NUM_DATA)
        async for item in result1.data:
            expected_item = next(expected_items_iter)
            assert_type(item, TextAndNum)  # type: ignore[client_tester_only]
            assert item == expected_item
        assert next(expected_items_iter, None) is None

        result2 = await client.foo_seq()
        assert_type(result2.data, AsyncIterator[TextAndNum])  # type: ignore[client_tester_only]
        expected_items_iter = iter(TEXT_AND_NUM_DATA)
        async for item in result2.data:
            expected_item = next(expected_items_iter)
            assert_type(item, TextAndNum)  # type: ignore[client_tester_only]
            assert item == expected_item
        assert next(expected_items_iter, None) is None

    await async_client_tester(app, client_test)
