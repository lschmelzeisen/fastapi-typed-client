from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI

from ..client_tester import AsyncClientTester, ClientTester
from ..shared import TextAndNum


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/foo")
    def foo() -> TextAndNum:
        return TextAndNum(text="foo", num=1)

    @app.get("/bar", status_code=HTTPStatus.CREATED.value)
    def bar() -> TextAndNum:
        return TextAndNum(text="bar", num=23)

    return app


@pytest.mark.parametrize("import_client_base", [False, True])
def test_normal_result(
    import_client_base: bool, app: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        from httpx import Response

        from ..shared import TextAndNum

        result = client.foo()

        assert_type(result.status, Literal[HTTPStatus.OK])  # type: ignore[client_tester_only]
        assert_type(result.data, TextAndNum)  # type: ignore[client_tester_only]
        assert_type(result.model, type[TextAndNum])  # type: ignore[client_tester_only]
        assert_type(result.response, Response)  # type: ignore[client_tester_only]
        assert result.status == HTTPStatus.OK
        assert result.data == TextAndNum(text="foo", num=1)
        assert result.model == TextAndNum
        assert result.response.url.path == "/foo"

    client_tester(app, client_test, import_client_base=import_client_base)


@pytest.mark.parametrize("import_client_base", [False, True])
async def test_normal_result_async(
    import_client_base: bool, app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        from httpx import Response

        from ..shared import TextAndNum

        result = await client.foo()

        assert_type(result.status, Literal[HTTPStatus.OK])  # type: ignore[client_tester_only]
        assert_type(result.data, TextAndNum)  # type: ignore[client_tester_only]
        assert_type(result.model, type[TextAndNum])  # type: ignore[client_tester_only]
        assert_type(result.response, Response)  # type: ignore[client_tester_only]
        assert result.status == HTTPStatus.OK
        assert result.data == TextAndNum(text="foo", num=1)
        assert result.model == TextAndNum
        assert result.response.url.path == "/foo"

    await async_client_tester(app, client_test, import_client_base=import_client_base)


def test_result_with_changed_status(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        from httpx import Response

        from ..shared import TextAndNum

        result = client.bar()

        assert_type(result.status, Literal[HTTPStatus.CREATED])  # type: ignore[client_tester_only]
        assert_type(result.data, TextAndNum)  # type: ignore[client_tester_only]
        assert_type(result.model, type[TextAndNum])  # type: ignore[client_tester_only]
        assert_type(result.response, Response)  # type: ignore[client_tester_only]
        assert result.status == HTTPStatus.CREATED
        assert result.data == TextAndNum(text="bar", num=23)
        assert result.model == TextAndNum
        assert result.response.url.path == "/bar"

    client_tester(app, client_test)


async def test_result_with_changed_status_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from http import HTTPStatus
        from typing import Literal, assert_type

        from httpx import Response

        from ..shared import TextAndNum

        result = await client.bar()

        assert_type(result.status, Literal[HTTPStatus.CREATED])  # type: ignore[client_tester_only]
        assert_type(result.data, TextAndNum)  # type: ignore[client_tester_only]
        assert_type(result.model, type[TextAndNum])  # type: ignore[client_tester_only]
        assert_type(result.response, Response)  # type: ignore[client_tester_only]
        assert result.status == HTTPStatus.CREATED
        assert result.data == TextAndNum(text="bar", num=23)
        assert result.model == TextAndNum
        assert result.response.url.path == "/bar"

    await async_client_tester(app, client_test)
