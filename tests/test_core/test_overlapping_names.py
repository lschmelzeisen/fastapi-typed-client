from typing import Any

import pytest
from fastapi import FastAPI

from ..client_tester import AsyncClientTester, ClientTester
from ..shared import FooBarEnum


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/foo")
    def builtin(int: int) -> str:  # noqa: A002
        return str(int)

    @app.get("/bar")
    def enum(FooBarEnum: FooBarEnum) -> int:  # noqa: N803
        return FooBarEnum.value

    return app


def test_builtin_param_name(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        assert client.builtin(2).data == "2"

    client_tester(
        app,
        client_test,
        assert_linting_passes=False,
        assert_format_of_generated_code=False,
    )


async def test_builtin_param_name_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        assert (await client.builtin(2)).data == "2"

    await async_client_tester(
        app,
        client_test,
        assert_linting_passes=False,
        assert_format_of_generated_code=False,
    )


def test_type_param_name(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import FooBarEnum

        assert client.enum(FooBarEnum=FooBarEnum.FOO).data == 123

    client_tester(
        app,
        client_test,
        assert_linting_passes=False,
        assert_format_of_generated_code=False,
    )
