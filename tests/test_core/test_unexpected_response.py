from collections.abc import Iterable
from http import HTTPStatus
from typing import Any

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.sse import EventSourceResponse
from fastapi.testclient import TestClient
from httpx2 import ASGITransport, AsyncClient, Response
from pydantic import ValidationError

from fastapi_typed_client import (
    FastAPIClientConflictingParamError,
    FastAPIClientError,
    FastAPIClientNotDefaultStatusError,
    FastAPIClientResult,
    FastAPIClientUnencodableParamError,
    FastAPIClientUnexpectedBody,
    FastAPIClientUnexpectedBodyError,
    FastAPIClientUnexpectedStatus,
    FastAPIClientUnexpectedStatusError,
    FastAPIClientUnexpectedStreamItem,
    FastAPIClientUnexpectedStreamItemError,
)

from ..client_tester import AsyncClientTester, ClientTester
from ..shared import TEXT_AND_NUM_DATA, TextAndNum


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/foo")
    def foo() -> TextAndNum:
        return TextAndNum(text="foo", num=1)

    @app.get("/problem", response_model=TextAndNum)
    def problem() -> JSONResponse:
        return JSONResponse(
            status_code=HTTPStatus.BAD_REQUEST.value,
            content={"title": "Bad Request", "status": 400},
            media_type="application/problem+json",
        )

    @app.get("/unavailable", response_model=TextAndNum)
    def unavailable() -> PlainTextResponse:
        return PlainTextResponse(
            "Down for maintenance",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE.value,
            headers={"Retry-After": "120"},
        )

    @app.get("/crash")
    def crash() -> TextAndNum:
        raise RuntimeError("Something went wrong.")

    @app.get("/unknown", response_model=TextAndNum)
    def unknown() -> PlainTextResponse:
        return PlainTextResponse(
            "Web server is returning an unknown error", status_code=520
        )

    return app


@pytest.fixture
def app_with_not_found() -> FastAPI:
    app = FastAPI()

    @app.get(
        "/item",
        response_model=TextAndNum,
        responses={HTTPStatus.NOT_FOUND.value: {"model": str}},
    )
    def item(name: str) -> JSONResponse:
        if name == "foo":
            return JSONResponse(content=TextAndNum(text="foo", num=1).model_dump())
        if name == "invalid":
            return JSONResponse(content={"text": "foo"})
        if name == "gone":
            return JSONResponse(
                status_code=HTTPStatus.NOT_FOUND.value,
                content={"detail": "Item not found"},
            )
        if name == "teapot":
            return JSONResponse(
                status_code=HTTPStatus.IM_A_TEAPOT.value,
                content={"detail": "I'm a teapot"},
            )
        return JSONResponse(
            status_code=HTTPStatus.NOT_FOUND.value,
            content=f"Item {name} not found",
        )

    return app


class _MaintenanceError(Exception):
    pass


def _raise_maintenance() -> None:
    raise _MaintenanceError


def _raise_gone() -> None:
    raise HTTPException(HTTPStatus.GONE.value, "Gone")


# Emits the given lines as-is, so that we can serve items that don't match the model.
class _RawJSONLinesResponse(StreamingResponse, JSONResponse):
    media_type = "application/jsonl"


@pytest.fixture
def app_with_streams() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(_MaintenanceError)
    def maintenance(_request: Request, _error: Exception) -> PlainTextResponse:
        return PlainTextResponse(
            "Down for maintenance", status_code=HTTPStatus.SERVICE_UNAVAILABLE.value
        )

    @app.get("/lines", response_model=TextAndNum)
    def lines() -> _RawJSONLinesResponse:
        return _RawJSONLinesResponse(
            [
                b'{"text": "foo", "num": 1}\n',
                b'{"text": "bar"}\n',
                b"{not json\n",
                b'{"text": "baz", "num": 456}\n',
            ]
        )

    @app.get("/lines-unavailable", dependencies=[Depends(_raise_maintenance)])
    def lines_unavailable() -> Iterable[TextAndNum]:
        yield from TEXT_AND_NUM_DATA

    @app.get(
        "/lines-gone",
        responses={HTTPStatus.GONE.value: {"model": list[str]}},
        dependencies=[Depends(_raise_gone)],
    )
    def lines_gone() -> Iterable[TextAndNum]:
        yield from TEXT_AND_NUM_DATA

    @app.get("/events", response_model=TextAndNum)
    def events() -> EventSourceResponse:
        return EventSourceResponse(
            [
                'id: 0\nevent: item\ndata: {"text": "foo", "num": 1}\n\n',
                'id: 1\nevent: item\ndata: {"text": "bar"}\n\n',
                'id: 2\nevent: item\ndata: {"text": "baz", "num": 456}\n\n',
            ]
        )

    @app.get(
        "/events-unavailable",
        response_class=EventSourceResponse,
        dependencies=[Depends(_raise_maintenance)],
    )
    def events_unavailable() -> Iterable[TextAndNum]:
        yield from TEXT_AND_NUM_DATA

    return app


# On most tests in this file, we set `import_client_base=True` so that we can import
# the unexpected response types and errors from `fastapi_typed_client` and actually
# implement the `assert_type` checks. Tests using `app_with_not_found` or
# `app_with_streams` set `assert_format_of_generated_code=False`, since these apps have
# routes with multiple responses, see test_multiple_responses.py for why. Tests
# importing from both `fastapi_typed_client` and `shared` set
# `assert_sorting_of_imports=False`, since `shared` becomes first-party in the generated
# test file.


def test_unexpected_status(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientNotDefaultStatusError,
            FastAPIClientUnexpectedStatus,
            FastAPIClientUnexpectedStatusError,
        )

        with pytest.raises(
            FastAPIClientUnexpectedStatusError, match="400 Bad Request"
        ) as error:
            client.problem()
        assert_type(error.value.result, FastAPIClientUnexpectedStatus)
        assert not isinstance(error.value, FastAPIClientNotDefaultStatusError)
        assert error.value.result.status == HTTPStatus.BAD_REQUEST
        assert error.value.result.data == {"title": "Bad Request", "status": 400}
        assert (
            error.value.result.response.headers["Content-Type"]
            == "application/problem+json"
        )

        with pytest.raises(
            FastAPIClientUnexpectedStatusError, match="503 Service Unavailable"
        ) as error:
            client.unavailable(raise_if_not_default_status=True)
        assert error.value.result.status == HTTPStatus.SERVICE_UNAVAILABLE
        assert error.value.result.data is None
        assert error.value.result.response.text == "Down for maintenance"
        assert error.value.result.response.headers["Retry-After"] == "120"

        with pytest.raises(
            FastAPIClientUnexpectedStatusError, match="500 Internal Server Error"
        ) as error:
            client.crash()
        assert error.value.result.status == HTTPStatus.INTERNAL_SERVER_ERROR
        assert error.value.result.data is None
        assert error.value.result.response.text == "Internal Server Error"

        with pytest.raises(
            FastAPIClientUnexpectedStatusError, match=r"520 \(non-standard\)"
        ) as error:
            client.unknown()
        assert error.value.result.status is None
        assert error.value.result.data is None
        assert error.value.result.response.status_code == 520
        assert (
            error.value.result.response.text
            == "Web server is returning an unknown error"
        )

    client_tester(
        app,
        client_test,
        import_client_base=True,
        httpx_client=TestClient(app, raise_server_exceptions=False),
    )


async def test_unexpected_status_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientNotDefaultStatusError,
            FastAPIClientUnexpectedStatus,
            FastAPIClientUnexpectedStatusError,
        )

        with pytest.raises(
            FastAPIClientUnexpectedStatusError, match="400 Bad Request"
        ) as error:
            await client.problem()
        assert_type(error.value.result, FastAPIClientUnexpectedStatus)
        assert not isinstance(error.value, FastAPIClientNotDefaultStatusError)
        assert error.value.result.status == HTTPStatus.BAD_REQUEST
        assert error.value.result.data == {"title": "Bad Request", "status": 400}
        assert (
            error.value.result.response.headers["Content-Type"]
            == "application/problem+json"
        )

        with pytest.raises(
            FastAPIClientUnexpectedStatusError, match="503 Service Unavailable"
        ) as error:
            await client.unavailable(raise_if_not_default_status=True)
        assert error.value.result.status == HTTPStatus.SERVICE_UNAVAILABLE
        assert error.value.result.data is None
        assert error.value.result.response.text == "Down for maintenance"
        assert error.value.result.response.headers["Retry-After"] == "120"

        with pytest.raises(
            FastAPIClientUnexpectedStatusError, match="500 Internal Server Error"
        ) as error:
            await client.crash()
        assert error.value.result.status == HTTPStatus.INTERNAL_SERVER_ERROR
        assert error.value.result.data is None
        assert error.value.result.response.text == "Internal Server Error"

        with pytest.raises(
            FastAPIClientUnexpectedStatusError, match=r"520 \(non-standard\)"
        ) as error:
            await client.unknown()
        assert error.value.result.status is None
        assert error.value.result.data is None
        assert error.value.result.response.status_code == 520
        assert (
            error.value.result.response.text
            == "Web server is returning an unknown error"
        )

    await async_client_tester(
        app,
        client_test,
        import_client_base=True,
        httpx_client=AsyncClient(
            transport=ASGITransport(app, raise_app_exceptions=False),
            base_url="http://testserver",
        ),
    )


def test_unexpected_status_renamed(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        import sys

        import pytest

        module = vars(sys.modules[type(client).__module__])

        with pytest.raises(Exception, match="400 Bad Request") as error:
            client.problem()
        assert type(error.value) is module["TestClientUnexpectedStatusError"]
        assert isinstance(error.value, module["TestClientUnexpectedResponseError"])
        assert isinstance(error.value, module["TestClientError"])

        result = client.problem(raise_if_unexpected_response=False)
        assert type(result) is module["TestClientUnexpectedStatus"]
        assert isinstance(result, module["TestClientUnexpectedResponse"])

    client_tester(app, client_test)


async def test_unexpected_status_renamed_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        import sys

        import pytest

        module = vars(sys.modules[type(client).__module__])

        with pytest.raises(Exception, match="400 Bad Request") as error:
            await client.problem()
        assert type(error.value) is module["TestClientUnexpectedStatusError"]
        assert isinstance(error.value, module["TestClientUnexpectedResponseError"])
        assert isinstance(error.value, module["TestClientError"])

        result = await client.problem(raise_if_unexpected_response=False)
        assert type(result) is module["TestClientUnexpectedStatus"]
        assert isinstance(result, module["TestClientUnexpectedResponse"])

    await async_client_tester(app, client_test)


def test_unexpected_status_returned(
    app_with_not_found: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        from fastapi_typed_client import (
            FastAPIClientHTTPValidationError,
            FastAPIClientResult,
            FastAPIClientUnexpectedBody,
            FastAPIClientUnexpectedResponse,
            FastAPIClientUnexpectedStatus,
        )

        from ..shared import TextAndNum

        result_teapot = client.item(name="teapot", raise_if_unexpected_response=False)
        assert_type(  # type: ignore[client_tester_only]
            result_teapot,
            FastAPIClientResult[Literal[HTTPStatus.OK], TextAndNum]
            | FastAPIClientResult[Literal[HTTPStatus.NOT_FOUND], str]
            | FastAPIClientResult[
                Literal[HTTPStatus.UNPROCESSABLE_CONTENT],
                FastAPIClientHTTPValidationError,
            ]
            | FastAPIClientUnexpectedStatus
            | FastAPIClientUnexpectedBody,
        )
        assert isinstance(result_teapot, FastAPIClientUnexpectedResponse)
        assert_type(  # type: ignore[client_tester_only]
            result_teapot, FastAPIClientUnexpectedStatus | FastAPIClientUnexpectedBody
        )
        assert isinstance(result_teapot, FastAPIClientUnexpectedStatus)
        assert result_teapot.status == HTTPStatus.IM_A_TEAPOT
        assert result_teapot.data == {"detail": "I'm a teapot"}

        result_missing = client.item(name="missing", raise_if_unexpected_response=False)
        assert not isinstance(result_missing, FastAPIClientUnexpectedResponse)
        assert result_missing.status == HTTPStatus.NOT_FOUND
        # Test type narrowing after we know the response status.
        assert_type(result_missing.data, str)  # type: ignore[client_tester_only]
        assert result_missing.data == "Item missing not found"

        result_default = client.item(
            name="teapot",
            raise_if_not_default_status=True,
            raise_if_unexpected_response=False,
        )
        assert_type(  # type: ignore[client_tester_only]
            result_default,
            FastAPIClientResult[Literal[HTTPStatus.OK], TextAndNum]
            | FastAPIClientUnexpectedStatus
            | FastAPIClientUnexpectedBody,
        )
        assert isinstance(result_default, FastAPIClientUnexpectedStatus)
        assert result_default.status == HTTPStatus.IM_A_TEAPOT

    client_tester(
        app_with_not_found,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


async def test_unexpected_status_returned_async(
    app_with_not_found: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        from fastapi_typed_client import (
            FastAPIClientHTTPValidationError,
            FastAPIClientResult,
            FastAPIClientUnexpectedBody,
            FastAPIClientUnexpectedResponse,
            FastAPIClientUnexpectedStatus,
        )

        from ..shared import TextAndNum

        result_teapot = await client.item(
            name="teapot", raise_if_unexpected_response=False
        )
        assert_type(  # type: ignore[client_tester_only]
            result_teapot,
            FastAPIClientResult[Literal[HTTPStatus.OK], TextAndNum]
            | FastAPIClientResult[Literal[HTTPStatus.NOT_FOUND], str]
            | FastAPIClientResult[
                Literal[HTTPStatus.UNPROCESSABLE_CONTENT],
                FastAPIClientHTTPValidationError,
            ]
            | FastAPIClientUnexpectedStatus
            | FastAPIClientUnexpectedBody,
        )
        assert isinstance(result_teapot, FastAPIClientUnexpectedResponse)
        assert_type(  # type: ignore[client_tester_only]
            result_teapot, FastAPIClientUnexpectedStatus | FastAPIClientUnexpectedBody
        )
        assert isinstance(result_teapot, FastAPIClientUnexpectedStatus)
        assert result_teapot.status == HTTPStatus.IM_A_TEAPOT
        assert result_teapot.data == {"detail": "I'm a teapot"}

        result_missing = await client.item(
            name="missing", raise_if_unexpected_response=False
        )
        assert not isinstance(result_missing, FastAPIClientUnexpectedResponse)
        assert result_missing.status == HTTPStatus.NOT_FOUND
        # Test type narrowing after we know the response status.
        assert_type(result_missing.data, str)  # type: ignore[client_tester_only]
        assert result_missing.data == "Item missing not found"

        result_default = await client.item(
            name="teapot",
            raise_if_not_default_status=True,
            raise_if_unexpected_response=False,
        )
        assert_type(  # type: ignore[client_tester_only]
            result_default,
            FastAPIClientResult[Literal[HTTPStatus.OK], TextAndNum]
            | FastAPIClientUnexpectedStatus
            | FastAPIClientUnexpectedBody,
        )
        assert isinstance(result_default, FastAPIClientUnexpectedStatus)
        assert result_default.status == HTTPStatus.IM_A_TEAPOT

    await async_client_tester(
        app_with_not_found,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


def test_raise_if_unexpected_response_default(
    app: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientResult,
            FastAPIClientUnexpectedBody,
            FastAPIClientUnexpectedStatus,
            FastAPIClientUnexpectedStatusError,
        )

        from ..shared import TextAndNum

        result = client.problem()
        assert_type(  # type: ignore[client_tester_only]
            result,
            FastAPIClientResult[Literal[HTTPStatus.OK], TextAndNum]
            | FastAPIClientUnexpectedStatus
            | FastAPIClientUnexpectedBody,
        )
        assert isinstance(result, FastAPIClientUnexpectedStatus)
        assert result.status == HTTPStatus.BAD_REQUEST

        result_raising = client.foo(raise_if_unexpected_response=True)
        assert_type(  # type: ignore[client_tester_only]
            result_raising, FastAPIClientResult[Literal[HTTPStatus.OK], TextAndNum]
        )
        assert result_raising.data == TextAndNum(text="foo", num=1)

        with pytest.raises(FastAPIClientUnexpectedStatusError):
            client.problem(raise_if_unexpected_response=True)

    client_tester(
        app,
        client_test,
        import_client_base=True,
        raise_if_unexpected_response=False,
        assert_sorting_of_imports=False,
    )


async def test_raise_if_unexpected_response_default_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientResult,
            FastAPIClientUnexpectedBody,
            FastAPIClientUnexpectedStatus,
            FastAPIClientUnexpectedStatusError,
        )

        from ..shared import TextAndNum

        result = await client.problem()
        assert_type(  # type: ignore[client_tester_only]
            result,
            FastAPIClientResult[Literal[HTTPStatus.OK], TextAndNum]
            | FastAPIClientUnexpectedStatus
            | FastAPIClientUnexpectedBody,
        )
        assert isinstance(result, FastAPIClientUnexpectedStatus)
        assert result.status == HTTPStatus.BAD_REQUEST

        result_raising = await client.foo(raise_if_unexpected_response=True)
        assert_type(  # type: ignore[client_tester_only]
            result_raising, FastAPIClientResult[Literal[HTTPStatus.OK], TextAndNum]
        )
        assert result_raising.data == TextAndNum(text="foo", num=1)

        with pytest.raises(FastAPIClientUnexpectedStatusError):
            await client.problem(raise_if_unexpected_response=True)

    await async_client_tester(
        app,
        client_test,
        import_client_base=True,
        raise_if_unexpected_response=False,
        assert_sorting_of_imports=False,
    )


def test_unexpected_body(
    app_with_not_found: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import assert_type

        import pytest
        from pydantic import ValidationError

        from fastapi_typed_client import (
            FastAPIClientUnexpectedBody,
            FastAPIClientUnexpectedBodyError,
        )

        from ..shared import TextAndNum

        with pytest.raises(
            FastAPIClientUnexpectedBodyError, match=r"200 OK.*`TextAndNum`"
        ) as error:
            client.item(name="invalid")
        assert_type(error.value.result, FastAPIClientUnexpectedBody)
        assert error.value.result.status == HTTPStatus.OK
        assert error.value.result.data == {"text": "foo"}
        assert error.value.result.model is TextAndNum
        assert isinstance(error.value.result.validation_error, ValidationError)
        assert error.value.__cause__ is error.value.result.validation_error

        # The unexpected body takes precedence over the non-default status.
        with pytest.raises(
            FastAPIClientUnexpectedBodyError, match=r"404 Not Found.*`str`"
        ) as error:
            client.item(name="gone", raise_if_not_default_status=True)
        assert error.value.result.status == HTTPStatus.NOT_FOUND
        assert error.value.result.data == {"detail": "Item not found"}
        assert error.value.result.model is str

        result = client.item(name="gone", raise_if_unexpected_response=False)
        assert isinstance(result, FastAPIClientUnexpectedBody)
        assert result.status == HTTPStatus.NOT_FOUND
        assert result.data == {"detail": "Item not found"}
        assert isinstance(result.validation_error, ValidationError)

    client_tester(
        app_with_not_found,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


async def test_unexpected_body_async(
    app_with_not_found: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import assert_type

        import pytest
        from pydantic import ValidationError

        from fastapi_typed_client import (
            FastAPIClientUnexpectedBody,
            FastAPIClientUnexpectedBodyError,
        )

        from ..shared import TextAndNum

        with pytest.raises(
            FastAPIClientUnexpectedBodyError, match=r"200 OK.*`TextAndNum`"
        ) as error:
            await client.item(name="invalid")
        assert_type(error.value.result, FastAPIClientUnexpectedBody)
        assert error.value.result.status == HTTPStatus.OK
        assert error.value.result.data == {"text": "foo"}
        assert error.value.result.model is TextAndNum
        assert isinstance(error.value.result.validation_error, ValidationError)
        assert error.value.__cause__ is error.value.result.validation_error

        # The unexpected body takes precedence over the non-default status.
        with pytest.raises(
            FastAPIClientUnexpectedBodyError, match=r"404 Not Found.*`str`"
        ) as error:
            await client.item(name="gone", raise_if_not_default_status=True)
        assert error.value.result.status == HTTPStatus.NOT_FOUND
        assert error.value.result.data == {"detail": "Item not found"}
        assert error.value.result.model is str

        result = await client.item(name="gone", raise_if_unexpected_response=False)
        assert isinstance(result, FastAPIClientUnexpectedBody)
        assert result.status == HTTPStatus.NOT_FOUND
        assert result.data == {"detail": "Item not found"}
        assert isinstance(result.validation_error, ValidationError)

    await async_client_tester(
        app_with_not_found,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


def test_stream_unexpected_response(
    app_with_streams: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import Iterator
        from http import HTTPStatus
        from typing import Literal, assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientResult,
            FastAPIClientUnexpectedBody,
            FastAPIClientUnexpectedBodyError,
            FastAPIClientUnexpectedStatus,
            FastAPIClientUnexpectedStatusError,
            FastAPIClientUnexpectedStreamItem,
        )

        from ..shared import TextAndNum

        with pytest.raises(
            FastAPIClientUnexpectedStatusError, match="503 Service Unavailable"
        ) as error:
            client.events_unavailable()
        assert error.value.result.data is None
        assert error.value.result.response.text == "Down for maintenance"
        assert error.value.result.response.is_closed

        result = client.lines_unavailable(raise_if_unexpected_response=False)
        assert_type(  # type: ignore[client_tester_only]
            result,
            FastAPIClientResult[
                Literal[HTTPStatus.OK],
                Iterator[TextAndNum | FastAPIClientUnexpectedStreamItem],
            ]
            | FastAPIClientUnexpectedStatus
            | FastAPIClientUnexpectedBody,
        )
        assert isinstance(result, FastAPIClientUnexpectedStatus)
        assert result.status == HTTPStatus.SERVICE_UNAVAILABLE
        assert result.data is None
        assert result.response.text == "Down for maintenance"
        assert result.response.is_closed

        with pytest.raises(
            FastAPIClientUnexpectedBodyError, match=r"410 Gone.*`list\[str\]`"
        ) as body_error:
            client.lines_gone()
        assert body_error.value.result.data == {"detail": "Gone"}
        assert body_error.value.result.response.text == '{"detail":"Gone"}'
        assert body_error.value.result.response.is_closed

    client_tester(
        app_with_streams,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


async def test_stream_unexpected_response_async(
    app_with_streams: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import AsyncIterator
        from http import HTTPStatus
        from typing import Literal, assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientResult,
            FastAPIClientUnexpectedBody,
            FastAPIClientUnexpectedBodyError,
            FastAPIClientUnexpectedStatus,
            FastAPIClientUnexpectedStatusError,
            FastAPIClientUnexpectedStreamItem,
        )

        from ..shared import TextAndNum

        with pytest.raises(
            FastAPIClientUnexpectedStatusError, match="503 Service Unavailable"
        ) as error:
            await client.events_unavailable()
        assert error.value.result.data is None
        assert error.value.result.response.text == "Down for maintenance"
        assert error.value.result.response.is_closed

        result = await client.lines_unavailable(raise_if_unexpected_response=False)
        assert_type(  # type: ignore[client_tester_only]
            result,
            FastAPIClientResult[
                Literal[HTTPStatus.OK],
                AsyncIterator[TextAndNum | FastAPIClientUnexpectedStreamItem],
            ]
            | FastAPIClientUnexpectedStatus
            | FastAPIClientUnexpectedBody,
        )
        assert isinstance(result, FastAPIClientUnexpectedStatus)
        assert result.status == HTTPStatus.SERVICE_UNAVAILABLE
        assert result.data is None
        assert result.response.text == "Down for maintenance"
        assert result.response.is_closed

        with pytest.raises(
            FastAPIClientUnexpectedBodyError, match=r"410 Gone.*`list\[str\]`"
        ) as body_error:
            await client.lines_gone()
        assert body_error.value.result.data == {"detail": "Gone"}
        assert body_error.value.result.response.text == '{"detail":"Gone"}'
        assert body_error.value.result.response.is_closed

    await async_client_tester(
        app_with_streams,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


def test_unexpected_json_lines_item(
    app_with_streams: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import Iterator
        from typing import assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientUnexpectedResponse,
            FastAPIClientUnexpectedStreamItem,
            FastAPIClientUnexpectedStreamItemError,
        )

        from ..shared import TextAndNum

        result = client.lines()
        assert next(result.data) == TextAndNum(text="foo", num=1)
        assert not result.response.is_closed
        with pytest.raises(
            FastAPIClientUnexpectedStreamItemError, match="`TextAndNum`"
        ) as error:
            next(result.data)
        assert_type(error.value.result, FastAPIClientUnexpectedStreamItem)
        assert error.value.result.raw == '{"text": "bar"}'
        assert error.value.result.data == {"text": "bar"}
        assert error.value.result.model is TextAndNum
        assert error.value.__cause__ is error.value.result.validation_error
        assert result.response.is_closed

        result_lenient = client.lines(raise_if_unexpected_response=False)
        assert not isinstance(result_lenient, FastAPIClientUnexpectedResponse)
        assert_type(  # type: ignore[client_tester_only]
            result_lenient.data,
            Iterator[TextAndNum | FastAPIClientUnexpectedStreamItem],
        )
        items = list(result_lenient.data)
        assert len(items) == 4
        assert items[0] == TextAndNum(text="foo", num=1)
        assert isinstance(items[1], FastAPIClientUnexpectedStreamItem)
        assert items[1].raw == '{"text": "bar"}'
        assert items[1].data == {"text": "bar"}
        assert isinstance(items[2], FastAPIClientUnexpectedStreamItem)
        assert items[2].raw == "{not json"
        assert items[2].data is None
        assert items[3] == TextAndNum(text="baz", num=456)

    client_tester(
        app_with_streams,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


async def test_unexpected_json_lines_item_async(
    app_with_streams: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import AsyncIterator
        from typing import assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientUnexpectedResponse,
            FastAPIClientUnexpectedStreamItem,
            FastAPIClientUnexpectedStreamItemError,
        )

        from ..shared import TextAndNum

        result = await client.lines()
        assert await anext(result.data) == TextAndNum(text="foo", num=1)
        assert not result.response.is_closed
        with pytest.raises(
            FastAPIClientUnexpectedStreamItemError, match="`TextAndNum`"
        ) as error:
            await anext(result.data)
        assert_type(error.value.result, FastAPIClientUnexpectedStreamItem)
        assert error.value.result.raw == '{"text": "bar"}'
        assert error.value.result.data == {"text": "bar"}
        assert error.value.result.model is TextAndNum
        assert error.value.__cause__ is error.value.result.validation_error
        assert result.response.is_closed

        result_lenient = await client.lines(raise_if_unexpected_response=False)
        assert not isinstance(result_lenient, FastAPIClientUnexpectedResponse)
        assert_type(  # type: ignore[client_tester_only]
            result_lenient.data,
            AsyncIterator[TextAndNum | FastAPIClientUnexpectedStreamItem],
        )
        items = [item async for item in result_lenient.data]
        assert len(items) == 4
        assert items[0] == TextAndNum(text="foo", num=1)
        assert isinstance(items[1], FastAPIClientUnexpectedStreamItem)
        assert items[1].raw == '{"text": "bar"}'
        assert items[1].data == {"text": "bar"}
        assert isinstance(items[2], FastAPIClientUnexpectedStreamItem)
        assert items[2].raw == "{not json"
        assert items[2].data is None
        assert items[3] == TextAndNum(text="baz", num=456)

    await async_client_tester(
        app_with_streams,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


def test_unexpected_sse_item(
    app_with_streams: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import Iterator
        from typing import assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientSSE,
            FastAPIClientUnexpectedResponse,
            FastAPIClientUnexpectedStreamItem,
            FastAPIClientUnexpectedStreamItemError,
        )

        from ..shared import TextAndNum

        result = client.events()
        assert next(result.data).data == TextAndNum(text="foo", num=1)
        assert not result.response.is_closed
        with pytest.raises(
            FastAPIClientUnexpectedStreamItemError, match="`TextAndNum`"
        ) as error:
            next(result.data)
        assert error.value.result.raw == '{"text": "bar"}'
        assert error.value.__cause__ is error.value.result.validation_error
        assert result.response.is_closed

        result_lenient = client.events(raise_if_unexpected_response=False)
        assert not isinstance(result_lenient, FastAPIClientUnexpectedResponse)
        assert_type(  # type: ignore[client_tester_only]
            result_lenient.data,
            Iterator[FastAPIClientSSE[TextAndNum | FastAPIClientUnexpectedStreamItem]],
        )
        events = list(result_lenient.data)
        assert [event.id for event in events] == ["0", "1", "2"]
        assert [event.event for event in events] == ["item", "item", "item"]
        assert events[0].data == TextAndNum(text="foo", num=1)
        assert isinstance(events[1].data, FastAPIClientUnexpectedStreamItem)
        assert events[1].data.raw == '{"text": "bar"}'
        assert events[1].data.data == {"text": "bar"}
        assert events[2].data == TextAndNum(text="baz", num=456)

    client_tester(
        app_with_streams,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


async def test_unexpected_sse_item_async(
    app_with_streams: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from collections.abc import AsyncIterator
        from typing import assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientSSE,
            FastAPIClientUnexpectedResponse,
            FastAPIClientUnexpectedStreamItem,
            FastAPIClientUnexpectedStreamItemError,
        )

        from ..shared import TextAndNum

        result = await client.events()
        assert (await anext(result.data)).data == TextAndNum(text="foo", num=1)
        assert not result.response.is_closed
        with pytest.raises(
            FastAPIClientUnexpectedStreamItemError, match="`TextAndNum`"
        ) as error:
            await anext(result.data)
        assert error.value.result.raw == '{"text": "bar"}'
        assert error.value.__cause__ is error.value.result.validation_error
        assert result.response.is_closed

        result_lenient = await client.events(raise_if_unexpected_response=False)
        assert not isinstance(result_lenient, FastAPIClientUnexpectedResponse)
        assert_type(  # type: ignore[client_tester_only]
            result_lenient.data,
            AsyncIterator[
                FastAPIClientSSE[TextAndNum | FastAPIClientUnexpectedStreamItem]
            ],
        )
        events = [event async for event in result_lenient.data]
        assert [event.id for event in events] == ["0", "1", "2"]
        assert [event.event for event in events] == ["item", "item", "item"]
        assert events[0].data == TextAndNum(text="foo", num=1)
        assert isinstance(events[1].data, FastAPIClientUnexpectedStreamItem)
        assert events[1].data.raw == '{"text": "bar"}'
        assert events[1].data.data == {"text": "bar"}
        assert events[2].data == TextAndNum(text="baz", num=456)

    await async_client_tester(
        app_with_streams,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


_RESPONSE = Response(HTTPStatus.BAD_REQUEST.value)
_VALIDATION_ERROR = ValidationError.from_exception_data(
    "int", [{"type": "int_parsing", "loc": (), "input": "foo"}]
)
_NOT_DEFAULT_STATUS_ERROR = FastAPIClientNotDefaultStatusError(
    default_status=HTTPStatus.OK,
    result=FastAPIClientResult(
        status=HTTPStatus.CREATED, data=1, model=int, response=_RESPONSE
    ),
)

_UNENCODABLE_PARAM_ERROR = FastAPIClientUnencodableParamError(
    location="header", name="foo", value=None, reason="bar"
)
_CONFLICTING_PARAM_ERROR = FastAPIClientConflictingParamError(
    location="header", name="foo"
)


@pytest.mark.parametrize(
    ("error", "attribute"),
    [
        pytest.param(
            _NOT_DEFAULT_STATUS_ERROR,
            "default_status",
            id="NotDefaultStatusError.default_status",
        ),
        pytest.param(
            _NOT_DEFAULT_STATUS_ERROR, "result", id="NotDefaultStatusError.result"
        ),
        pytest.param(
            FastAPIClientUnexpectedStatusError(
                result=FastAPIClientUnexpectedStatus(
                    status=HTTPStatus.BAD_REQUEST, data=None, response=_RESPONSE
                )
            ),
            "result",
            id="UnexpectedStatusError.result",
        ),
        pytest.param(
            FastAPIClientUnexpectedBodyError(
                result=FastAPIClientUnexpectedBody(
                    status=HTTPStatus.OK,
                    data="foo",
                    model=int,
                    validation_error=_VALIDATION_ERROR,
                    response=_RESPONSE,
                )
            ),
            "result",
            id="UnexpectedBodyError.result",
        ),
        pytest.param(
            FastAPIClientUnexpectedStreamItemError(
                result=FastAPIClientUnexpectedStreamItem(
                    data="foo",
                    raw='"foo"',
                    model=int,
                    validation_error=_VALIDATION_ERROR,
                )
            ),
            "result",
            id="UnexpectedStreamItemError.result",
        ),
        pytest.param(
            _UNENCODABLE_PARAM_ERROR, "location", id="UnencodableParamError.location"
        ),
        pytest.param(_UNENCODABLE_PARAM_ERROR, "name", id="UnencodableParamError.name"),
        pytest.param(
            _UNENCODABLE_PARAM_ERROR, "value", id="UnencodableParamError.value"
        ),
        pytest.param(
            _CONFLICTING_PARAM_ERROR, "location", id="ConflictingParamError.location"
        ),
        pytest.param(_CONFLICTING_PARAM_ERROR, "name", id="ConflictingParamError.name"),
    ],
)
def test_error_attributes_are_read_only(
    error: FastAPIClientError, attribute: str
) -> None:
    with pytest.raises(AttributeError):
        setattr(error, attribute, None)
