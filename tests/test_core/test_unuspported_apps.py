from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, Header, Query
from fastapi.openapi.models import SecurityBase as SecurityBaseModel
from fastapi.openapi.models import SecuritySchemeType
from fastapi.security import HTTPDigest, OAuth2
from fastapi.security.base import SecurityBase

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
    raises=RuntimeError,
    reason=(
        "Same Python parameter name declared in different kinds (Query vs Header) "
        "collides in the generated client signature; could in principle be "
        "supported by sending the same value to both locations, but not yet."
    ),
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
    raises=RuntimeError,
    reason=(
        "Same Python parameter name declared in different kinds (Query vs Header) "
        "collides in the generated client signature; could in principle be "
        "supported by sending the same value to both locations, but not yet."
    ),
)
def test_route_with_multiple_duplicate_parameter_names() -> None:
    app = FastAPI()

    def dependency(foo: Annotated[str, Query()], bar: Annotated[str, Query()]) -> None:
        pass

    @app.get("/", dependencies=[Depends(dependency)])
    def endpoint(foo: Annotated[str, Header()], bar: Annotated[str, Header()]) -> None:
        pass

    generate_fastapi_typed_client(app)


@pytest.mark.xfail(
    raises=RuntimeError,
    reason=(
        "HTTPDigest is a challenge-response scheme and can not be reduced to a "
        "static header; not supported yet."
    ),
)
def test_route_with_http_digest_security() -> None:
    app = FastAPI()

    @app.get("/", dependencies=[Depends(HTTPDigest())])
    def endpoint() -> None:
        pass

    generate_fastapi_typed_client(app)


@pytest.mark.xfail(
    raises=RuntimeError,
    reason=(
        "The OAuth2 base class (with custom flows) is not supported yet; use one of "
        "OAuth2PasswordBearer / OAuth2AuthorizationCodeBearer / OpenIdConnect."
    ),
)
def test_route_with_oauth2_base_security() -> None:
    app = FastAPI()

    @app.get("/", dependencies=[Depends(OAuth2(flows={}))])
    def endpoint() -> None:
        pass

    generate_fastapi_typed_client(app)


@pytest.mark.xfail(
    raises=RuntimeError,
    reason="Custom SecurityBase subclasses are not supported yet.",
)
def test_route_with_custom_security_base() -> None:
    class CustomAuth(SecurityBase):
        def __init__(self) -> None:
            self.scheme_name = "CustomAuth"
            self.model = SecurityBaseModel(type=SecuritySchemeType.http)

        def __call__(self) -> str:
            return "ok"

    app = FastAPI()

    @app.get("/", dependencies=[Depends(CustomAuth())])
    def endpoint() -> None:
        pass

    generate_fastapi_typed_client(app)
