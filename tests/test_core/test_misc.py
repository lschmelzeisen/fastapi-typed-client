from typing import Any

import pytest
from fastapi import FastAPI

from ..client_tester import AsyncClientTester, ClientTester


@pytest.fixture
def app_with_index() -> FastAPI:
    app = FastAPI()

    @app.get("/")
    def endpoint() -> str:
        return "index"

    return app


def test_app_with_index(app_with_index: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        assert client.endpoint().data == "index"

    client_tester(app_with_index, client_test)


async def test_app_with_index_async(
    app_with_index: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        assert (await client.endpoint()).data == "index"

    await async_client_tester(app_with_index, client_test)
