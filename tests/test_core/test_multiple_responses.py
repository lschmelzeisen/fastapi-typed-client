from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..client_tester import AsyncClientTester, ClientTester


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get(
        "/foo", response_model=str, responses={HTTPStatus.CREATED.value: {"model": int}}
    )
    def foo(created: bool = False) -> JSONResponse:
        if created:
            return JSONResponse(status_code=HTTPStatus.CREATED.value, content=123)
        return JSONResponse(content="foo")

    return app


@pytest.fixture
def app_with_diff_default_status() -> FastAPI:
    app = FastAPI()

    @app.get(
        "/foo",
        status_code=HTTPStatus.ACCEPTED.value,
        response_model=str,
        responses={HTTPStatus.CREATED.value: {"model": int}},
    )
    def foo(created: bool = False) -> JSONResponse:
        if created:
            return JSONResponse(status_code=HTTPStatus.CREATED.value, content=123)
        return JSONResponse(status_code=HTTPStatus.ACCEPTED.value, content="foo")

    return app


# On all tests in this file, we set:
# - import_client_base=True so that we can import `FastAPIClientResult` from
#   `fastapi_typed_client` and actually implement the `assert_type` checks.
# - assert_format_of_generated_code=False because the code for return types of multiple
#   responses does not follow ruff's expected format (but instead one that is better
#   suited to reduce diffs on changes to an endpoint's responses).


def test_types(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        from fastapi_typed_client import (
            FastAPIClientHTTPValidationError,
            FastAPIClientResult,
        )

        result1 = client.foo()
        assert_type(  # type: ignore[client_tester_only]
            result1,
            FastAPIClientResult[Literal[HTTPStatus.OK], str]
            | FastAPIClientResult[Literal[HTTPStatus.CREATED], int]
            | FastAPIClientResult[
                Literal[HTTPStatus.UNPROCESSABLE_CONTENT],
                FastAPIClientHTTPValidationError,
            ],
        )
        assert result1.status == HTTPStatus.OK
        # Test type narrowing after we know the response status.
        assert_type(result1.data, str)  # type: ignore[client_tester_only]
        assert result1.data == "foo"

        result2 = client.foo(created=True)
        assert_type(  # type: ignore[client_tester_only]
            result2,
            FastAPIClientResult[Literal[HTTPStatus.OK], str]
            | FastAPIClientResult[Literal[HTTPStatus.CREATED], int]
            | FastAPIClientResult[
                Literal[HTTPStatus.UNPROCESSABLE_CONTENT],
                FastAPIClientHTTPValidationError,
            ],
        )
        assert result2.status == HTTPStatus.CREATED
        # Test type narrowing after we know the response status.
        assert_type(result2.data, int)  # type: ignore[client_tester_only]
        assert result2.data == 123

    client_tester(
        app,
        client_test,
        import_client_base=True,
        assert_format_of_generated_code=False,
    )


async def test_types_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        from fastapi_typed_client import (
            FastAPIClientHTTPValidationError,
            FastAPIClientResult,
        )

        result1 = await client.foo()
        assert_type(  # type: ignore[client_tester_only]
            result1,
            FastAPIClientResult[Literal[HTTPStatus.OK], str]
            | FastAPIClientResult[Literal[HTTPStatus.CREATED], int]
            | FastAPIClientResult[
                Literal[HTTPStatus.UNPROCESSABLE_CONTENT],
                FastAPIClientHTTPValidationError,
            ],
        )
        assert result1.status == HTTPStatus.OK
        # Test type narrowing after we know the response status.
        assert_type(result1.data, str)  # type: ignore[client_tester_only]
        assert result1.data == "foo"

        result2 = await client.foo(created=True)
        assert_type(  # type: ignore[client_tester_only]
            result2,
            FastAPIClientResult[Literal[HTTPStatus.OK], str]
            | FastAPIClientResult[Literal[HTTPStatus.CREATED], int]
            | FastAPIClientResult[
                Literal[HTTPStatus.UNPROCESSABLE_CONTENT],
                FastAPIClientHTTPValidationError,
            ],
        )
        assert result2.status == HTTPStatus.CREATED
        # Test type narrowing after we know the response status.
        assert_type(result2.data, int)  # type: ignore[client_tester_only]
        assert result2.data == 123

    await async_client_tester(
        app,
        client_test,
        import_client_base=True,
        assert_format_of_generated_code=False,
    )


def test_raise_if_not_default_status(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientNotDefaultStatusError,
            FastAPIClientResult,
        )

        result = client.foo(raise_if_not_default_status=True)
        assert_type(  # type: ignore[client_tester_only]
            result, FastAPIClientResult[Literal[HTTPStatus.OK], str]
        )
        assert result.status == HTTPStatus.OK
        assert result.data == "foo"

        with pytest.raises(FastAPIClientNotDefaultStatusError) as error:
            client.foo(created=True, raise_if_not_default_status=True)
        assert error.value.default_status == HTTPStatus.OK
        assert error.value.result.status == HTTPStatus.CREATED
        assert error.value.result.data == 123

    client_tester(
        app,
        client_test,
        import_client_base=True,
        assert_format_of_generated_code=False,
    )


async def test_raise_if_not_default_status_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientNotDefaultStatusError,
            FastAPIClientResult,
        )

        result = await client.foo(raise_if_not_default_status=True)
        assert_type(  # type: ignore[client_tester_only]
            result, FastAPIClientResult[Literal[HTTPStatus.OK], str]
        )
        assert result.status == HTTPStatus.OK
        assert result.data == "foo"

        with pytest.raises(FastAPIClientNotDefaultStatusError) as error:
            await client.foo(created=True, raise_if_not_default_status=True)
        assert error.value.default_status == HTTPStatus.OK
        assert error.value.result.status == HTTPStatus.CREATED
        assert error.value.result.data == 123

    await async_client_tester(
        app,
        client_test,
        import_client_base=True,
        assert_format_of_generated_code=False,
    )


def test_raise_if_not_default_status_default(
    app: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        from fastapi_typed_client import (
            FastAPIClientHTTPValidationError,
            FastAPIClientResult,
        )

        result1 = client.foo()
        assert_type(  # type: ignore[client_tester_only]
            result1, FastAPIClientResult[Literal[HTTPStatus.OK], str]
        )

        result2 = client.foo(raise_if_not_default_status=False)
        assert_type(  # type: ignore[client_tester_only]
            result2,
            FastAPIClientResult[Literal[HTTPStatus.OK], str]
            | FastAPIClientResult[Literal[HTTPStatus.CREATED], int]
            | FastAPIClientResult[
                Literal[HTTPStatus.UNPROCESSABLE_CONTENT],
                FastAPIClientHTTPValidationError,
            ],
        )

    client_tester(
        app,
        client_test,
        import_client_base=True,
        raise_if_not_default_status=True,
        assert_format_of_generated_code=False,
    )


async def test_raise_if_not_default_status_default_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        from fastapi_typed_client import (
            FastAPIClientHTTPValidationError,
            FastAPIClientResult,
        )

        result1 = await client.foo()
        assert_type(  # type: ignore[client_tester_only]
            result1, FastAPIClientResult[Literal[HTTPStatus.OK], str]
        )

        result2 = await client.foo(raise_if_not_default_status=False)
        assert_type(  # type: ignore[client_tester_only]
            result2,
            FastAPIClientResult[Literal[HTTPStatus.OK], str]
            | FastAPIClientResult[Literal[HTTPStatus.CREATED], int]
            | FastAPIClientResult[
                Literal[HTTPStatus.UNPROCESSABLE_CONTENT],
                FastAPIClientHTTPValidationError,
            ],
        )

    await async_client_tester(
        app,
        client_test,
        import_client_base=True,
        raise_if_not_default_status=True,
        assert_format_of_generated_code=False,
    )


def test_with_diff_default_status(
    app_with_diff_default_status: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientHTTPValidationError,
            FastAPIClientNotDefaultStatusError,
            FastAPIClientResult,
        )

        result1 = client.foo()
        assert_type(  # type: ignore[client_tester_only]
            result1,
            FastAPIClientResult[Literal[HTTPStatus.ACCEPTED], str]
            | FastAPIClientResult[Literal[HTTPStatus.CREATED], int]
            | FastAPIClientResult[
                Literal[HTTPStatus.UNPROCESSABLE_CONTENT],
                FastAPIClientHTTPValidationError,
            ],
        )
        assert result1.status == HTTPStatus.ACCEPTED
        assert result1.data == "foo"

        result2 = client.foo(raise_if_not_default_status=True)
        assert_type(  # type: ignore[client_tester_only]
            result2, FastAPIClientResult[Literal[HTTPStatus.ACCEPTED], str]
        )
        assert result2.status == HTTPStatus.ACCEPTED
        assert result2.data == "foo"

        with pytest.raises(FastAPIClientNotDefaultStatusError) as error:
            client.foo(created=True, raise_if_not_default_status=True)
        assert error.value.default_status == HTTPStatus.ACCEPTED
        assert error.value.result.status == HTTPStatus.CREATED
        assert error.value.result.data == 123

    client_tester(
        app_with_diff_default_status,
        client_test,
        import_client_base=True,
        assert_format_of_generated_code=False,
    )


async def test_with_diff_default_status_async(
    app_with_diff_default_status: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        import pytest

        from fastapi_typed_client import (
            FastAPIClientHTTPValidationError,
            FastAPIClientNotDefaultStatusError,
            FastAPIClientResult,
        )

        result1 = await client.foo()
        assert_type(  # type: ignore[client_tester_only]
            result1,
            FastAPIClientResult[Literal[HTTPStatus.ACCEPTED], str]
            | FastAPIClientResult[Literal[HTTPStatus.CREATED], int]
            | FastAPIClientResult[
                Literal[HTTPStatus.UNPROCESSABLE_CONTENT],
                FastAPIClientHTTPValidationError,
            ],
        )
        assert result1.status == HTTPStatus.ACCEPTED
        assert result1.data == "foo"

        result2 = await client.foo(raise_if_not_default_status=True)
        assert_type(  # type: ignore[client_tester_only]
            result2, FastAPIClientResult[Literal[HTTPStatus.ACCEPTED], str]
        )
        assert result2.status == HTTPStatus.ACCEPTED
        assert result2.data == "foo"

        with pytest.raises(FastAPIClientNotDefaultStatusError) as error:
            await client.foo(created=True, raise_if_not_default_status=True)
        assert error.value.default_status == HTTPStatus.ACCEPTED
        assert error.value.result.status == HTTPStatus.CREATED
        assert error.value.result.data == 123

    await async_client_tester(
        app_with_diff_default_status,
        client_test,
        import_client_base=True,
        assert_format_of_generated_code=False,
    )
