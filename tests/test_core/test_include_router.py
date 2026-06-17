from pathlib import Path
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Depends, FastAPI, Query
from fastapi.security import HTTPBearer

from fastapi_typed_client import generate_fastapi_typed_client

from ..client_tester import AsyncClientTester, ClientTester


@pytest.fixture
def app_with_included_router() -> FastAPI:
    app = FastAPI()

    @app.get("/direct")
    def direct() -> str:
        return "direct"

    router = APIRouter(prefix="/sub")

    @router.get("/items/{item_id}")
    def get_item(item_id: int) -> int:
        return item_id

    app.include_router(router)
    return app


@pytest.fixture
def app_with_nested_routers() -> FastAPI:
    app = FastAPI()
    inner = APIRouter(prefix="/inner")

    @inner.get("/ping")
    def ping() -> str:
        return "pong"

    outer = APIRouter(prefix="/outer")
    outer.include_router(inner)
    app.include_router(outer)
    return app


def _require_query(marker: Annotated[str, Query()]) -> str:
    return marker


@pytest.fixture
def app_with_router_dependency() -> FastAPI:
    app = FastAPI()
    router = APIRouter(prefix="/secured", dependencies=[Depends(_require_query)])

    @router.get("/resource")
    def resource() -> str:
        return "resource"

    app.include_router(router)
    return app


@pytest.fixture
def app_with_router_security() -> FastAPI:
    app = FastAPI()
    router = APIRouter(prefix="/secured", dependencies=[Depends(HTTPBearer())])

    @router.get("/resource")
    def resource() -> str:
        return "resource"

    app.include_router(router)
    return app


def test_included_router_routes_are_generated(
    app_with_included_router: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        assert client.direct().data == "direct"
        result = client.get_item(item_id=42)
        assert result.data == 42
        assert result.response.request.url.path == "/sub/items/42"

    client_tester(
        app_with_included_router, client_test, assert_format_of_generated_code=False
    )


async def test_included_router_routes_are_generated_async(
    app_with_included_router: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        assert (await client.direct()).data == "direct"
        result = await client.get_item(item_id=42)
        assert result.data == 42
        assert result.response.request.url.path == "/sub/items/42"

    await async_client_tester(
        app_with_included_router, client_test, assert_format_of_generated_code=False
    )


def test_nested_included_routers(
    app_with_nested_routers: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        result = client.ping()
        assert result.data == "pong"
        assert result.response.request.url.path == "/outer/inner/ping"

    client_tester(app_with_nested_routers, client_test)


async def test_nested_included_routers_async(
    app_with_nested_routers: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        result = await client.ping()
        assert result.data == "pong"
        assert result.response.request.url.path == "/outer/inner/ping"

    await async_client_tester(app_with_nested_routers, client_test)


def test_router_level_dependency_propagates(
    app_with_router_dependency: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        sig = signature(client.resource)
        assert sig.parameters["marker"].annotation is str
        assert sig.parameters["marker"].default is Parameter.empty

        result = client.resource(marker="hello")
        assert result.response.url.params.get("marker") == "hello"
        assert result.data == "resource"

    client_tester(
        app_with_router_dependency, client_test, assert_format_of_generated_code=False
    )


async def test_router_level_dependency_propagates_async(
    app_with_router_dependency: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        sig = signature(client.resource)
        assert sig.parameters["marker"].annotation is str
        assert sig.parameters["marker"].default is Parameter.empty

        result = await client.resource(marker="hello")
        assert result.response.url.params.get("marker") == "hello"
        assert result.data == "resource"

    await async_client_tester(
        app_with_router_dependency, client_test, assert_format_of_generated_code=False
    )


def test_router_level_security_propagates(
    app_with_router_security: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import signature

        assert "http_bearer" in signature(client.resource).parameters

        result = client.resource(http_bearer="t0k3n")
        assert result.response.request.headers["authorization"] == "Bearer t0k3n"
        assert result.data == "resource"

    client_tester(
        app_with_router_security, client_test, assert_format_of_generated_code=False
    )


async def test_router_level_security_propagates_async(
    app_with_router_security: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import signature

        assert "http_bearer" in signature(client.resource).parameters

        result = await client.resource(http_bearer="t0k3n")
        assert result.response.request.headers["authorization"] == "Bearer t0k3n"
        assert result.data == "resource"

    await async_client_tester(
        app_with_router_security, client_test, assert_format_of_generated_code=False
    )


@pytest.mark.usefixtures("tmp_cwd")
def test_bare_router_passed_directly_with_nested_include() -> None:
    # The generator also accepts an `APIRouter` directly; nested `include_router` calls
    # on it must be walked too.
    top = APIRouter()

    @top.get("/top")
    def top_endpoint() -> str:
        return "top"

    child = APIRouter(prefix="/child")

    @child.get("/leaf")
    def leaf() -> str:
        return "leaf"

    top.include_router(child)

    generate_fastapi_typed_client(top)

    generated = Path("fastapi_client.py").read_text(encoding="utf-8")
    assert "def top_endpoint(" in generated
    assert "def leaf(" in generated
    assert "/child/leaf" in generated
