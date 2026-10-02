from collections.abc import AsyncIterable, Iterable
from http import HTTPStatus
from typing import Any

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

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


@pytest.fixture
def app_with_lower_additional_status() -> FastAPI:
    app = FastAPI()

    # The additional `200 OK` response sorts before the default `201 Created` one.
    @app.post(
        "/foo", status_code=HTTPStatus.CREATED.value, responses={200: {"model": str}}
    )
    def foo() -> Iterable[TextAndNum]:
        yield from TEXT_AND_NUM_DATA

    return app


# Sets `import_client_base=True` to import `FastAPIClientResult` for `assert_type` and
# `assert_format_of_generated_code=False`, see test_multiple_responses.py for why.


def test_stream_json_lines_lower_additional_status(
    app_with_lower_additional_status: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import Iterator
        from http import HTTPStatus
        from typing import Literal, assert_type

        from fastapi_typed_client import FastAPIClientResult

        from ..shared import TEXT_AND_NUM_DATA, TextAndNum

        result = client.foo()
        assert_type(  # type: ignore[client_tester_only]
            result,
            FastAPIClientResult[Literal[HTTPStatus.OK], str]
            | FastAPIClientResult[Literal[HTTPStatus.CREATED], Iterator[TextAndNum]],
        )
        assert result.status == HTTPStatus.CREATED
        assert list(result.data) == TEXT_AND_NUM_DATA

    client_tester(
        app_with_lower_additional_status,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


async def test_stream_json_lines_lower_additional_status_async(
    app_with_lower_additional_status: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import AsyncIterator
        from http import HTTPStatus
        from typing import Literal, assert_type

        from fastapi_typed_client import FastAPIClientResult

        from ..shared import TEXT_AND_NUM_DATA, TextAndNum

        result = await client.foo()
        assert_type(  # type: ignore[client_tester_only]
            result,
            FastAPIClientResult[Literal[HTTPStatus.OK], str]
            | FastAPIClientResult[
                Literal[HTTPStatus.CREATED], AsyncIterator[TextAndNum]
            ],
        )
        assert result.status == HTTPStatus.CREATED
        assert [item async for item in result.data] == TEXT_AND_NUM_DATA

    await async_client_tester(
        app_with_lower_additional_status,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


class _NotFoundError(Exception):
    pass


@pytest.fixture
def app_with_not_found() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(_NotFoundError)
    def handle_not_found(_request: Request, _exc: _NotFoundError) -> JSONResponse:
        return JSONResponse("Not found", status_code=HTTPStatus.NOT_FOUND.value)

    def raise_not_found() -> None:
        raise _NotFoundError

    @app.get(
        "/foo",
        responses={HTTPStatus.NOT_FOUND.value: {"model": str}},
        dependencies=[Depends(raise_not_found)],
    )
    def foo() -> Iterable[TextAndNum]:
        yield from TEXT_AND_NUM_DATA

    return app


def test_stream_json_lines_not_default_status(
    app_with_not_found: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus

        result = client.foo()
        assert result.status == HTTPStatus.NOT_FOUND
        assert result.data == "Not found"
        assert result.response.text == '"Not found"'
        assert result.response.is_closed

    client_tester(
        app_with_not_found, client_test, assert_format_of_generated_code=False
    )


async def test_stream_json_lines_not_default_status_async(
    app_with_not_found: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus

        result = await client.foo()
        assert result.status == HTTPStatus.NOT_FOUND
        assert result.data == "Not found"
        assert result.response.text == '"Not found"'
        assert result.response.is_closed

    await async_client_tester(
        app_with_not_found, client_test, assert_format_of_generated_code=False
    )
