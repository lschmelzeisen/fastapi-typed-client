from collections.abc import Sequence
from math import ceil
from typing import Annotated, Any
from uuid import UUID

import pytest
from fastapi import Body, Cookie, FastAPI, Header, Query
from pydantic import Field

from ..client_tester import AsyncClientTester, ClientTester
from ..shared import TEXT_AND_NUM_DATA, TextAndNum, TextAndNumDefault


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/query-params")
    def query_params(text: str, num: float = 3.0) -> str:
        return f"{text}{'=' * ceil(num)}{num:.2f}"

    @app.get("/query-param-with-model")
    def query_param_with_model(query: Annotated[TextAndNumDefault, Query()]) -> str:
        return f"{query.text}-{query.num}"

    @app.get("/query-param-list")
    def query_param_list(nums: Annotated[Sequence[int], Query()]) -> str:
        return ",".join(map(str, nums))

    @app.post("/path-params/{text}-{num}")
    def path_params(text: str, num: float) -> str:
        return f"{text}-{num:.2f}"

    @app.get("/header-param")
    def header_param(my_param: Annotated[str, Header(alias="X-My-Param")]) -> str:
        return my_param

    @app.get("/cookie-param")
    def cookie_param(session_id: Annotated[UUID, Cookie()]) -> str:
        return str(session_id)

    return app


@pytest.fixture
def app_with_body_routes() -> FastAPI:
    app = FastAPI()

    @app.get("/unembedded")
    def unembedded(param: Annotated[TextAndNum, Body()]) -> str:
        return f"{param.text}-{param.num}"

    @app.get("/unembedded-default-param")
    def unembedded_default(
        param: Annotated[TextAndNum, Body()] = TEXT_AND_NUM_DATA[0],
    ) -> str:
        return f"{param.text}-{param.num}"

    @app.get("/embedded")
    def embedded(param: Annotated[TextAndNum, Body(embed=True)]) -> str:
        return f"{param.text}-{param.num}"

    @app.get("/embedded-default-param")
    def embedded_default(
        param: Annotated[TextAndNum, Body(embed=True)] = TEXT_AND_NUM_DATA[0],
    ) -> str:
        return f"{param.text}-{param.num}"

    @app.get("/multiple")
    def multiple(
        param1: Annotated[TextAndNum, Body()], param2: Annotated[TextAndNum, Body()]
    ) -> str:
        return f"{param1.text}-{param1.num}:{param2.text}-{param2.num}"

    return app


@pytest.fixture
def app_wih_validation() -> FastAPI:
    app = FastAPI()

    @app.get("/value-gt-0")
    def value_gt_0(value: Annotated[int, Field(gt=0)]) -> int:
        return value

    return app


def test_query_param_and_required_and_optional_params(
    app: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        assert client.query_params("foo").data == "foo===3.00"
        assert client.query_params("foo", 0.5).data == "foo=0.50"

        foo_signature = signature(client.query_params)
        foo_param_text = foo_signature.parameters["text"]
        foo_param_num = foo_signature.parameters["num"]
        assert foo_param_text.default is Parameter.empty
        assert foo_param_text.annotation is str
        assert foo_param_text.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert foo_param_num.default is not Parameter.empty
        assert foo_param_num.annotation is float
        assert foo_param_num.kind is Parameter.POSITIONAL_OR_KEYWORD

    client_tester(app, client_test, assert_format_of_generated_code=False)


async def test_query_param_and_required_and_optional_params_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        assert (await client.query_params("foo")).data == "foo===3.00"
        assert (await client.query_params("foo", 0.5)).data == "foo=0.50"

        foo_signature = signature(client.query_params)
        foo_param_text = foo_signature.parameters["text"]
        foo_param_num = foo_signature.parameters["num"]
        assert foo_param_text.default is Parameter.empty
        assert foo_param_text.annotation is str
        assert foo_param_text.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert foo_param_num.default is not Parameter.empty
        assert foo_param_num.annotation is float
        assert foo_param_num.kind is Parameter.POSITIONAL_OR_KEYWORD

    await async_client_tester(app, client_test, assert_format_of_generated_code=False)


def test_query_model(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from httpx import QueryParams

        result1 = client.query_param_with_model(text="fooquux", num=123)
        assert result1.response.url.params == QueryParams(
            {"text": "fooquux", "num": 123}
        )
        assert result1.data == "fooquux-123"

        result2 = client.query_param_with_model()
        assert not result2.response.url.params
        assert result2.data == "foobarbaz-4"

    client_tester(app, client_test, assert_format_of_generated_code=False)


async def test_query_model_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from httpx import QueryParams

        result1 = await client.query_param_with_model(text="fooquux", num=123)
        assert result1.response.url.params == QueryParams(
            {"text": "fooquux", "num": 123}
        )
        assert result1.data == "fooquux-123"

        result2 = await client.query_param_with_model()
        assert not result2.response.url.params
        assert result2.data == "foobarbaz-4"

    await async_client_tester(app, client_test, assert_format_of_generated_code=False)


def test_query_list(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from httpx import QueryParams

        result = client.query_param_list([123, 4, 56])
        assert result.response.url.params == QueryParams({"nums": [123, 4, 56]})
        assert result.data == "123,4,56"

    client_tester(app, client_test, assert_format_of_generated_code=False)


async def test_query_list_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from httpx import QueryParams

        result = await client.query_param_list([123, 4, 56])
        assert result.response.url.params == QueryParams({"nums": [123, 4, 56]})
        assert result.data == "123,4,56"

    await async_client_tester(app, client_test, assert_format_of_generated_code=False)


def test_path_param_and_post_method(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        result = client.path_params(text="foobar", num=13)
        assert result.response.url.path == "/path-params/foobar-13"
        assert result.response.request.method == "POST"
        assert result.data == "foobar-13.00"

    client_tester(app, client_test, assert_format_of_generated_code=False)


async def test_path_param_and_post_method_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        result = await client.path_params(text="foobar", num=13)
        assert result.response.url.path == "/path-params/foobar-13"
        assert result.response.request.method == "POST"
        assert result.data == "foobar-13.00"

    await async_client_tester(app, client_test, assert_format_of_generated_code=False)


def test_header_param_and_param_with_alias(
    app: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        result = client.header_param(my_param="foobar")
        assert result.response.request.headers["X-My-Param"] == "foobar"
        assert result.response.request.method == "GET"
        assert result.data == "foobar"

    client_tester(app, client_test, assert_format_of_generated_code=False)


async def test_header_param_and_param_with_alias_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        result = await client.header_param(my_param="foobar")
        assert result.response.request.headers["X-My-Param"] == "foobar"
        assert result.response.request.method == "GET"
        assert result.data == "foobar"

    await async_client_tester(app, client_test, assert_format_of_generated_code=False)


def test_cookie_param_and_uuid_param(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from uuid import uuid4

        import pytest

        session_id = uuid4()
        with (
            pytest.warns(UserWarning, match="cookie parameter"),
            pytest.warns(DeprecationWarning, match="per-request cookie"),
        ):
            result = client.cookie_param(session_id=session_id)
        assert result.data == str(session_id)
        assert result.response.request.headers["cookie"] == f"session_id={session_id}"

    client_tester(app, client_test, assert_format_of_generated_code=False)


async def test_cookie_param_and_uuid_param_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from uuid import uuid4

        import pytest

        session_id = uuid4()
        with (
            pytest.warns(UserWarning, match="cookie parameter"),
            pytest.warns(DeprecationWarning, match="per-request cookie"),
        ):
            result = await client.cookie_param(session_id=session_id)
        assert result.data == str(session_id)
        assert result.response.request.headers["cookie"] == f"session_id={session_id}"

    await async_client_tester(app, client_test, assert_format_of_generated_code=False)


def test_body_param_unembedded(
    app_with_body_routes: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum

        result = client.unembedded(TextAndNum(text="foobar", num=789))
        assert result.response.request.content == b'{"text":"foobar","num":789}'
        assert result.data == "foobar-789"

    client_tester(
        app_with_body_routes, client_test, assert_format_of_generated_code=False
    )


async def test_body_param_unembedded_async(
    app_with_body_routes: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum

        result = await client.unembedded(TextAndNum(text="foobar", num=789))
        assert result.response.request.content == b'{"text":"foobar","num":789}'
        assert result.data == "foobar-789"

    await async_client_tester(
        app_with_body_routes, client_test, assert_format_of_generated_code=False
    )


def test_body_param_unembedded_default(
    app_with_body_routes: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        result = client.unembedded_default()
        assert result.response.request.content == b""
        assert result.data == "foo-1"

    client_tester(
        app_with_body_routes, client_test, assert_format_of_generated_code=False
    )


async def test_body_param_unembedded_default_async(
    app_with_body_routes: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        result = await client.unembedded_default()
        assert result.response.request.content == b""
        assert result.data == "foo-1"

    await async_client_tester(
        app_with_body_routes, client_test, assert_format_of_generated_code=False
    )


def test_body_param_embedded(
    app_with_body_routes: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum

        result = client.embedded(TextAndNum(text="foobar", num=789))
        assert (
            result.response.request.content == b'{"param":{"text":"foobar","num":789}}'
        )
        assert result.data == "foobar-789"

    client_tester(
        app_with_body_routes, client_test, assert_format_of_generated_code=False
    )


async def test_body_param_embedded_async(
    app_with_body_routes: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum

        result = await client.embedded(TextAndNum(text="foobar", num=789))
        assert (
            result.response.request.content == b'{"param":{"text":"foobar","num":789}}'
        )
        assert result.data == "foobar-789"

    await async_client_tester(
        app_with_body_routes, client_test, assert_format_of_generated_code=False
    )


def test_body_param_embedded_default(
    app_with_body_routes: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        result = client.embedded_default()
        assert result.response.request.content == b""
        assert result.data == "foo-1"

    client_tester(
        app_with_body_routes, client_test, assert_format_of_generated_code=False
    )


async def test_body_param_embedded_default_async(
    app_with_body_routes: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        result = await client.embedded_default()
        assert result.response.request.content == b""
        assert result.data == "foo-1"

    await async_client_tester(
        app_with_body_routes, client_test, assert_format_of_generated_code=False
    )


def test_body_param_multiple(
    app_with_body_routes: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum

        result = client.multiple(
            param1=TextAndNum(text="foo", num=1), param2=TextAndNum(text="bar", num=2)
        )
        assert (
            result.response.request.content
            == b'{"param1":{"text":"foo","num":1},"param2":{"text":"bar","num":2}}'
        )
        assert result.data == "foo-1:bar-2"

    client_tester(
        app_with_body_routes, client_test, assert_format_of_generated_code=False
    )


async def test_body_param_multiple_async(
    app_with_body_routes: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum

        result = await client.multiple(
            param1=TextAndNum(text="foo", num=1), param2=TextAndNum(text="bar", num=2)
        )
        assert (
            result.response.request.content
            == b'{"param1":{"text":"foo","num":1},"param2":{"text":"bar","num":2}}'
        )
        assert result.data == "foo-1:bar-2"

    await async_client_tester(
        app_with_body_routes, client_test, assert_format_of_generated_code=False
    )


def test_validation_error(
    app_wih_validation: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus

        from fastapi_typed_client import (
            FastAPIClientHTTPValidationError,
            FastAPIClientValidationError,
        )

        result = client.value_gt_0(-1)
        assert result.status == HTTPStatus.UNPROCESSABLE_CONTENT
        assert result.data == FastAPIClientHTTPValidationError(
            detail=[
                FastAPIClientValidationError(
                    loc=["query", "value"],
                    msg="Input should be greater than 0",
                    type="greater_than",
                )
            ]
        )
        assert result.model == FastAPIClientHTTPValidationError

    with pytest.warns(UserWarning, match="Pydantic FieldInfo"):
        client_tester(
            app_wih_validation,
            client_test,
            import_client_base=True,
            assert_format_of_generated_code=False,
        )


async def test_validation_error_async(
    app_wih_validation: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus

        from fastapi_typed_client import (
            FastAPIClientHTTPValidationError,
            FastAPIClientValidationError,
        )

        result = await client.value_gt_0(-1)
        assert result.status == HTTPStatus.UNPROCESSABLE_CONTENT
        assert result.data == FastAPIClientHTTPValidationError(
            detail=[
                FastAPIClientValidationError(
                    loc=["query", "value"],
                    msg="Input should be greater than 0",
                    type="greater_than",
                )
            ]
        )
        assert result.model == FastAPIClientHTTPValidationError

    with pytest.warns(UserWarning, match="Pydantic FieldInfo"):
        await async_client_tester(
            app_wih_validation,
            client_test,
            import_client_base=True,
            assert_format_of_generated_code=False,
        )
