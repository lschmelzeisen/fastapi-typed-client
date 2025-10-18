from typing import Any
from unittest.mock import Mock

import pytest
from fastapi import FastAPI

from ..client_tester import AsyncClientTester, ClientTester


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/foo")
    def foo() -> str:
        return "foo"

    return app


# This has no async equivalent, because the warning is only thrown in the sync case.
def test_from_app_timeout_warning(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        import pytest

        with pytest.deprecated_call():
            client.foo(client_exts={"timeout": 1.0})

    client_tester(app, client_test)


def test_timeout_passed_to_httpx_client(
    app: FastAPI, client_tester: ClientTester
) -> None:
    httpx_client_mock = Mock()
    httpx_client_mock.request = Mock(side_effect=RuntimeError())

    def client_test(client: Any) -> None:  # noqa: ANN401
        client.foo(client_exts={"timeout": 10.0})

    with pytest.raises(RuntimeError):
        client_tester(app, client_test, httpx_client=httpx_client_mock)
    httpx_client_mock.request.assert_called_once()
    assert httpx_client_mock.request.call_args.kwargs["timeout"] == 10.0


async def test_timeout_passed_to_httpx_client_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    httpx_client_mock = Mock()
    httpx_client_mock.request = Mock(side_effect=RuntimeError())

    async def client_test(client: Any) -> None:  # noqa: ANN401
        await client.foo(client_exts={"timeout": 10.0})

    with pytest.raises(RuntimeError):
        await async_client_tester(app, client_test, httpx_client=httpx_client_mock)
    httpx_client_mock.request.assert_called_once()
    assert httpx_client_mock.request.call_args.kwargs["timeout"] == 10.0
