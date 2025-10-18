from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, Header, Query

from fastapi_typed_client import generate_fastapi_typed_client

pytestmark = pytest.mark.usefixtures("tmp_cwd")


@pytest.mark.xfail(
    raises=RuntimeError, reason="Routes with non-identifiers names not supported yet"
)
def test_route_with_non_identifier_name() -> None:
    app = FastAPI()

    @app.get("/", name="end point")
    def endpoint() -> None:
        pass

    generate_fastapi_typed_client(app)


@pytest.mark.xfail(
    raises=RuntimeError, reason="Routes with duplicate names not supported yet"
)
def test_duplicate_route_names() -> None:
    app = FastAPI()

    @app.get("/")
    def endpoint() -> None:
        pass

    @app.post("/", name="endpoint")
    def endpoint2() -> None:
        pass

    generate_fastapi_typed_client(app)


@pytest.mark.xfail(
    raises=RuntimeError, reason="Routes with multiple methods not supported yet"
)
def test_route_with_multiple_methods() -> None:
    app = FastAPI()

    @app.api_route("/", methods=["GET", "POST"])
    def endpoint() -> None:
        pass

    generate_fastapi_typed_client(app)


@pytest.mark.xfail(
    raises=RuntimeError, reason="Routes with duplicate parameters are not supported yet"
)
def test_route_with_single_duplicate_parameter_names() -> None:
    app = FastAPI()

    def dependency(foo: Annotated[str, Query()]) -> None:
        pass

    @app.get("/", dependencies=[Depends(dependency)])
    def endpoint(foo: Annotated[str, Header()]) -> None:
        pass

    generate_fastapi_typed_client(app)


@pytest.mark.xfail(
    raises=RuntimeError, reason="Routes with duplicate parameters are not supported yet"
)
def test_route_with_multiple_duplicate_parameter_names() -> None:
    app = FastAPI()

    def dependency(foo: Annotated[str, Query()], bar: Annotated[str, Query()]) -> None:
        pass

    @app.get("/", dependencies=[Depends(dependency)])
    def endpoint(foo: Annotated[str, Header()], bar: Annotated[str, Header()]) -> None:
        pass

    generate_fastapi_typed_client(app)
