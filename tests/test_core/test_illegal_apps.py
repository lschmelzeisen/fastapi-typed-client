import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from fastapi_typed_client import generate_fastapi_typed_client

pytestmark = pytest.mark.usefixtures("tmp_cwd")


def test_no_routes() -> None:
    app = FastAPI()

    with pytest.raises(RuntimeError):
        generate_fastapi_typed_client(app)


def test_route_without_methods() -> None:
    app = FastAPI()

    @app.get("/")
    def endpoint() -> None:
        pass

    route = next(
        r for r in app.routes if isinstance(r, APIRoute) and r.name == endpoint.__name__
    )
    route.methods.clear()

    with pytest.raises(RuntimeError):
        generate_fastapi_typed_client(app)


def test_route_with_empty_path() -> None:
    app = FastAPI()

    @app.get("")
    def endpoint() -> None:
        pass

    with pytest.raises(RuntimeError):
        generate_fastapi_typed_client(app)


def test_route_with_single_disallowed_param_name() -> None:
    app = FastAPI()

    @app.get("/")
    def endpoint(client_exts: str) -> None:
        pass

    with pytest.raises(RuntimeError):
        generate_fastapi_typed_client(app)


def test_route_with_multiple_disallowed_param_name() -> None:
    app = FastAPI()

    @app.get("/")
    def endpoint(client_exts: str, raise_if_not_default_status: bool) -> None:
        pass

    with pytest.raises(RuntimeError):
        generate_fastapi_typed_client(app)
