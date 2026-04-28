from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.sse import EventSourceResponse, ServerSentEvent

from ..client_tester import AsyncClientTester, ClientTester
from ..shared import TEXT_AND_NUM_DATA, TextAndNum


async def _baz_gen() -> AsyncIterator[str]:
    for item in TEXT_AND_NUM_DATA:
        yield f"data: {item.model_dump_json()}\n\n"


async def _qux_gen() -> AsyncIterator[str]:
    for i, item in enumerate(TEXT_AND_NUM_DATA):
        yield (
            "event: text-and-num\n"
            f"id: {i}\n"
            "retry: 2500\n"
            f"data: {item.model_dump_json()}\n\n"
        )


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/foo", response_class=EventSourceResponse)
    async def foo() -> AsyncIterable[TextAndNum]:
        for item in TEXT_AND_NUM_DATA:
            yield item

    @app.get("/bar", response_class=EventSourceResponse)
    async def bar() -> AsyncIterable[ServerSentEvent]:
        yield ServerSentEvent(comment="start")
        for i, item in enumerate(TEXT_AND_NUM_DATA):
            yield ServerSentEvent(
                data=item, event="text-and-num", id=str(i), retry=5000
            )

    @app.get("/baz", response_model=TextAndNum)
    def baz() -> EventSourceResponse:
        return EventSourceResponse(_baz_gen())

    @app.get("/qux")
    def qux() -> EventSourceResponse:
        return EventSourceResponse(_qux_gen())

    return app


# `import_client_base=True` is used so we can import `FastAPIClientSSE`
# from `fastapi_typed_client` (instead of having to refer to the renamed identifier
# inside the generated client) and actually implement the `assert_type` checks.


def test_stream_sse(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import Iterator
        from typing import Any, assert_type

        from fastapi_typed_client import FastAPIClientSSE

        from ..shared import TEXT_AND_NUM_DATA, TextAndNum

        result_typed = client.foo()
        assert_type(  # type: ignore[client_tester_only]
            result_typed.data,
            Iterator[FastAPIClientSSE[TextAndNum]],
        )
        for event, expected_item in zip(
            result_typed.data, TEXT_AND_NUM_DATA, strict=True
        ):
            assert_type(event, FastAPIClientSSE[TextAndNum])  # type: ignore[client_tester_only]
            assert_type(event.data, TextAndNum | None)  # type: ignore[client_tester_only]
            assert event.data == expected_item

        result_events = client.bar()
        assert_type(  # type: ignore[client_tester_only]
            result_events.data,
            Iterator[FastAPIClientSSE[Any]],
        )
        events = list(result_events.data)
        assert events[0].comment == "start"
        for event, (i, expected_item) in zip(
            events[1:], enumerate(TEXT_AND_NUM_DATA), strict=True
        ):
            assert event.event == "text-and-num"
            assert event.id == str(i)
            assert event.retry == 5000
            assert event.data == expected_item.model_dump()

        result_direct_typed = client.baz()
        assert_type(  # type: ignore[client_tester_only]
            result_direct_typed.data,
            Iterator[FastAPIClientSSE[TextAndNum]],
        )
        for event, expected_item in zip(
            result_direct_typed.data, TEXT_AND_NUM_DATA, strict=True
        ):
            assert_type(event, FastAPIClientSSE[TextAndNum])  # type: ignore[client_tester_only]
            assert_type(event.data, TextAndNum | None)  # type: ignore[client_tester_only]
            assert event.data == expected_item

        result_direct_untyped = client.qux()
        assert_type(  # type: ignore[client_tester_only]
            result_direct_untyped.data,
            Iterator[FastAPIClientSSE[Any]],
        )
        for event, (i, expected_item) in zip(
            result_direct_untyped.data, enumerate(TEXT_AND_NUM_DATA), strict=True
        ):
            assert event.event == "text-and-num"
            assert event.id == str(i)
            assert event.retry == 2500
            assert event.data == expected_item.model_dump()

    client_tester(
        app, client_test, import_client_base=True, assert_sorting_of_imports=False
    )


async def test_stream_sse_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import AsyncIterator
        from typing import Any, assert_type

        from fastapi_typed_client import FastAPIClientSSE

        from ..shared import TEXT_AND_NUM_DATA, TextAndNum

        result_typed = await client.foo()
        assert_type(  # type: ignore[client_tester_only]
            result_typed.data,
            AsyncIterator[FastAPIClientSSE[TextAndNum]],
        )
        expected_iter = iter(TEXT_AND_NUM_DATA)
        async for event in result_typed.data:
            expected = next(expected_iter)
            assert_type(event, FastAPIClientSSE[TextAndNum])  # type: ignore[client_tester_only]
            assert_type(event.data, TextAndNum | None)  # type: ignore[client_tester_only]
            assert event.data == expected
        assert next(expected_iter, None) is None

        result_events = await client.bar()
        assert_type(  # type: ignore[client_tester_only]
            result_events.data,
            AsyncIterator[FastAPIClientSSE[Any]],
        )
        events: list[Any] = []
        async for event in result_events.data:
            events.append(event)
        assert events[0].comment == "start"
        for event, (i, expected_item) in zip(
            events[1:], enumerate(TEXT_AND_NUM_DATA), strict=True
        ):
            assert event.event == "text-and-num"
            assert event.id == str(i)
            assert event.retry == 5000
            assert event.data == expected_item.model_dump()

        # Direct-return EventSourceResponse with `response_model` → typed payload.
        result_direct_typed = await client.baz()
        assert_type(  # type: ignore[client_tester_only]
            result_direct_typed.data,
            AsyncIterator[FastAPIClientSSE[TextAndNum]],
        )
        expected_iter = iter(TEXT_AND_NUM_DATA)
        async for event in result_direct_typed.data:
            expected = next(expected_iter)
            assert_type(event, FastAPIClientSSE[TextAndNum])  # type: ignore[client_tester_only]
            assert_type(event.data, TextAndNum | None)  # type: ignore[client_tester_only]
            assert event.data == expected
        assert next(expected_iter, None) is None

        # Direct-return EventSourceResponse without `response_model` → Any.
        result_direct_untyped = await client.qux()
        assert_type(  # type: ignore[client_tester_only]
            result_direct_untyped.data,
            AsyncIterator[FastAPIClientSSE[Any]],
        )
        expected_iter = iter(TEXT_AND_NUM_DATA)
        i = 0
        async for event in result_direct_untyped.data:
            expected = next(expected_iter)
            assert event.event == "text-and-num"
            assert event.id == str(i)
            assert event.retry == 2500
            assert event.data == expected.model_dump()
            i += 1
        assert next(expected_iter, None) is None

    await async_client_tester(
        app, client_test, import_client_base=True, assert_sorting_of_imports=False
    )
