from typing import Annotated, Any

import pytest
from fastapi import Cookie, Depends, FastAPI, Header, Query
from fastapi.security import (
    APIKeyCookie,
    APIKeyHeader,
    APIKeyQuery,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
    OpenIdConnect,
)
from fastapi.security.http import HTTPAuthorizationCredentials

from ..client_tester import AsyncClientTester, ClientTester


@pytest.fixture
def app_http_bearer() -> FastAPI:
    app = FastAPI()

    @app.get("/bearer")
    def endpoint(
        creds: Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())],
    ) -> str:
        return f"{creds.scheme} {creds.credentials}"

    return app


@pytest.fixture
def app_http_basic() -> FastAPI:
    app = FastAPI()

    @app.get("/basic")
    def endpoint(creds: Annotated[HTTPBasicCredentials, Depends(HTTPBasic())]) -> str:
        return f"{creds.username}:{creds.password}"

    return app


@pytest.fixture
def app_api_key_header() -> FastAPI:
    app = FastAPI()

    @app.get("/api-key-header")
    def endpoint(key: Annotated[str, Depends(APIKeyHeader(name="X-API-Key"))]) -> str:
        return key

    return app


@pytest.fixture
def app_api_key_cookie() -> FastAPI:
    app = FastAPI()

    @app.get("/api-key-cookie")
    def endpoint(key: Annotated[str, Depends(APIKeyCookie(name="session_id"))]) -> str:
        return key

    return app


@pytest.fixture
def app_api_key_query() -> FastAPI:
    app = FastAPI()

    @app.get("/api-key-query")
    def endpoint(key: Annotated[str, Depends(APIKeyQuery(name="api_key"))]) -> str:
        return key

    return app


@pytest.fixture
def app_oauth2_password_bearer() -> FastAPI:
    app = FastAPI()

    @app.get("/oauth2")
    def endpoint(
        token: Annotated[str, Depends(OAuth2PasswordBearer(tokenUrl="/token"))],
    ) -> str:
        return token

    return app


@pytest.fixture
def app_oauth2_password_request_form() -> FastAPI:
    app = FastAPI()

    @app.post("/token")
    def endpoint(
        form: Annotated[OAuth2PasswordRequestForm, Depends()],
    ) -> dict[str, Any]:
        return {
            "username": form.username,
            "password": form.password,
            "scopes": form.scopes,
            "grant_type": form.grant_type,
        }

    return app


@pytest.fixture
def app_openid_connect() -> FastAPI:
    app = FastAPI()

    @app.get("/oidc")
    def endpoint(
        token: Annotated[
            str,
            Depends(
                OpenIdConnect(
                    openIdConnectUrl="https://example.com/.well-known/openid-configuration"
                )
            ),
        ],
    ) -> str:
        return token

    return app


@pytest.fixture
def app_invalid_security_params() -> FastAPI:
    app = FastAPI()

    @app.get("/bearer")
    def bearer(
        creds: Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())],
    ) -> str:
        return creds.credentials

    @app.get("/basic")
    def basic(creds: Annotated[HTTPBasicCredentials, Depends(HTTPBasic())]) -> str:
        return creds.username

    @app.get("/api-key-header")
    def api_key_header(
        key: Annotated[str, Depends(APIKeyHeader(name="X-API-Key"))],
        other: Annotated[str | None, Header(alias="x-api-key")] = None,
    ) -> str:
        return f"{key}-{other}"

    @app.get("/api-key-cookie")
    def api_key_cookie(
        key: Annotated[str, Depends(APIKeyCookie(name="session"))],
        other: Annotated[str | None, Cookie(alias="session")] = None,
    ) -> str:
        return f"{key}-{other}"

    @app.get("/api-key-query")
    def api_key_query(
        key: Annotated[str, Depends(APIKeyQuery(name="api_key"))],
        other: Annotated[str | None, Query(alias="api_key")] = None,
    ) -> str:
        return f"{key}-{other}"

    @app.get("/two-schemes")
    def two_schemes(
        creds: Annotated[
            HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))
        ],
        key: Annotated[
            str | None, Depends(APIKeyHeader(name="authorization", auto_error=False))
        ],
    ) -> str:
        return f"{creds}-{key}"

    return app


@pytest.fixture
def app_shared_scheme() -> FastAPI:
    app = FastAPI()
    bearer = HTTPBearer()

    def dep_a(
        creds: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    ) -> str:
        return f"a-{creds.credentials}"

    def dep_b(
        creds: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    ) -> str:
        return f"b-{creds.credentials}"

    @app.get("/shared")
    def endpoint(
        a: Annotated[str, Depends(dep_a)], b: Annotated[str, Depends(dep_b)]
    ) -> str:
        return f"{a}|{b}"

    return app


@pytest.fixture
def app_multiple_schemes() -> FastAPI:
    app = FastAPI()

    @app.get("/multi")
    def endpoint(
        creds: Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())],
        key: Annotated[str, Depends(APIKeyHeader(name="X-API-Key"))],
    ) -> str:
        return f"{creds.credentials}|{key}"

    return app


@pytest.fixture
def app_auto_error_false() -> FastAPI:
    app = FastAPI()

    @app.get("/optional-bearer")
    def endpoint(
        creds: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(HTTPBearer(auto_error=False, scheme_name="OptionalBearer")),
        ],
    ) -> str:
        if creds is None:
            return "none"
        return f"{creds.scheme} {creds.credentials}"

    return app


@pytest.fixture
def app_implicit_scheme_on_decorator() -> FastAPI:
    app = FastAPI()

    @app.get("/bearer", dependencies=[Depends(HTTPBearer())])
    def endpoint() -> str:
        return "ok"

    return app


@pytest.fixture
def app_explicit_scheme_on_decorator() -> FastAPI:
    app = FastAPI()

    @app.get(
        "/decorator-bearer",
        dependencies=[Depends(HTTPBearer(scheme_name="DecoratorBearer"))],
    )
    def endpoint() -> str:
        return "ok"

    return app


def test_http_bearer(app_http_bearer: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = client.endpoint("t0k3n")
        assert result.response.request.headers["authorization"] == "Bearer t0k3n"
        assert result.data == "Bearer t0k3n"

        sig = signature(client.endpoint)
        assert sig.parameters["creds"].annotation is str
        assert sig.parameters["creds"].default is Parameter.empty

    client_tester(app_http_bearer, client_test, assert_format_of_generated_code=False)


async def test_http_bearer_async(
    app_http_bearer: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = await client.endpoint("t0k3n")
        assert result.response.request.headers["authorization"] == "Bearer t0k3n"
        assert result.data == "Bearer t0k3n"

        sig = signature(client.endpoint)
        assert sig.parameters["creds"].annotation is str
        assert sig.parameters["creds"].default is Parameter.empty

    await async_client_tester(
        app_http_bearer, client_test, assert_format_of_generated_code=False
    )


def test_http_basic(app_http_basic: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from base64 import b64decode
        from inspect import Parameter, signature

        result = client.endpoint(("alice", "s3cret"))
        header = result.response.request.headers["authorization"]
        assert header.startswith("Basic ")
        assert b64decode(header.removeprefix("Basic ")).decode() == "alice:s3cret"
        assert result.data == "alice:s3cret"

        sig = signature(client.endpoint)
        assert sig.parameters["creds"].annotation == tuple[str, str]
        assert sig.parameters["creds"].default is Parameter.empty

    client_tester(app_http_basic, client_test, assert_format_of_generated_code=False)


async def test_http_basic_async(
    app_http_basic: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from base64 import b64decode
        from inspect import Parameter, signature

        result = await client.endpoint(("alice", "s3cret"))
        header = result.response.request.headers["authorization"]
        assert header.startswith("Basic ")
        assert b64decode(header.removeprefix("Basic ")).decode() == "alice:s3cret"
        assert result.data == "alice:s3cret"

        sig = signature(client.endpoint)
        assert sig.parameters["creds"].annotation == tuple[str, str]
        assert sig.parameters["creds"].default is Parameter.empty

    await async_client_tester(
        app_http_basic, client_test, assert_format_of_generated_code=False
    )


def test_api_key_header(
    app_api_key_header: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = client.endpoint("secret-key")
        assert result.response.request.headers["x-api-key"] == "secret-key"
        assert result.data == "secret-key"

        sig = signature(client.endpoint)
        assert sig.parameters["key"].annotation is str
        assert sig.parameters["key"].default is Parameter.empty

    client_tester(
        app_api_key_header, client_test, assert_format_of_generated_code=False
    )


async def test_api_key_header_async(
    app_api_key_header: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = await client.endpoint("secret-key")
        assert result.response.request.headers["x-api-key"] == "secret-key"
        assert result.data == "secret-key"

        sig = signature(client.endpoint)
        assert sig.parameters["key"].annotation is str
        assert sig.parameters["key"].default is Parameter.empty

    await async_client_tester(
        app_api_key_header, client_test, assert_format_of_generated_code=False
    )


def test_api_key_cookie(
    app_api_key_cookie: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        import pytest

        with pytest.warns(DeprecationWarning, match="per-request cookie"):
            result = client.endpoint("abc123")
        assert result.response.request.headers["cookie"] == "session_id=abc123"
        assert result.data == "abc123"

        sig = signature(client.endpoint)
        assert sig.parameters["key"].annotation is str
        assert sig.parameters["key"].default is Parameter.empty

    client_tester(
        app_api_key_cookie, client_test, assert_format_of_generated_code=False
    )


async def test_api_key_cookie_async(
    app_api_key_cookie: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        import pytest

        with pytest.warns(DeprecationWarning, match="per-request cookie"):
            result = await client.endpoint("abc123")
        assert result.response.request.headers["cookie"] == "session_id=abc123"
        assert result.data == "abc123"

        sig = signature(client.endpoint)
        assert sig.parameters["key"].annotation is str
        assert sig.parameters["key"].default is Parameter.empty

    await async_client_tester(
        app_api_key_cookie, client_test, assert_format_of_generated_code=False
    )


def test_api_key_query(app_api_key_query: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = client.endpoint("xyz789")
        assert result.response.url.params.get("api_key") == "xyz789"
        assert result.data == "xyz789"

        sig = signature(client.endpoint)
        assert sig.parameters["key"].annotation is str
        assert sig.parameters["key"].default is Parameter.empty

    client_tester(app_api_key_query, client_test, assert_format_of_generated_code=False)


async def test_api_key_query_async(
    app_api_key_query: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = await client.endpoint("xyz789")
        assert result.response.url.params.get("api_key") == "xyz789"
        assert result.data == "xyz789"

        sig = signature(client.endpoint)
        assert sig.parameters["key"].annotation is str
        assert sig.parameters["key"].default is Parameter.empty

    await async_client_tester(
        app_api_key_query, client_test, assert_format_of_generated_code=False
    )


def test_oauth2_password_bearer(
    app_oauth2_password_bearer: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = client.endpoint("oauth-token")
        assert result.response.request.headers["authorization"] == "Bearer oauth-token"
        assert result.data == "oauth-token"

        sig = signature(client.endpoint)
        assert sig.parameters["token"].annotation is str
        assert sig.parameters["token"].default is Parameter.empty

    client_tester(
        app_oauth2_password_bearer,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_oauth2_password_bearer_async(
    app_oauth2_password_bearer: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = await client.endpoint("oauth-token")
        assert result.response.request.headers["authorization"] == "Bearer oauth-token"
        assert result.data == "oauth-token"

        sig = signature(client.endpoint)
        assert sig.parameters["token"].annotation is str
        assert sig.parameters["token"].default is Parameter.empty

    await async_client_tester(
        app_oauth2_password_bearer,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_oauth2_password_request_form(
    app_oauth2_password_request_form: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from httpx2 import QueryParams

        password = "s3cret"  # noqa: S105
        result = client.endpoint(username="alice", password=password)
        assert (
            result.response.request.headers["content-type"]
            == "application/x-www-form-urlencoded"
        )
        assert dict(QueryParams(result.response.request.content)) == {
            "username": "alice",
            "password": password,
        }
        assert result.data == {
            "username": "alice",
            "password": password,
            "scopes": [],
            "grant_type": None,
        }

        result2 = client.endpoint(
            username="bob", password=password, grant_type="password", scope="read write"
        )
        assert result2.data == {
            "username": "bob",
            "password": password,
            "scopes": ["read", "write"],
            "grant_type": "password",
        }

    client_tester(
        app_oauth2_password_request_form,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_oauth2_password_request_form_async(
    app_oauth2_password_request_form: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from httpx2 import QueryParams

        password = "s3cret"  # noqa: S105
        result = await client.endpoint(username="alice", password=password)
        assert (
            result.response.request.headers["content-type"]
            == "application/x-www-form-urlencoded"
        )
        assert dict(QueryParams(result.response.request.content)) == {
            "username": "alice",
            "password": password,
        }
        assert result.data == {
            "username": "alice",
            "password": password,
            "scopes": [],
            "grant_type": None,
        }

        result2 = await client.endpoint(
            username="bob", password=password, grant_type="password", scope="read write"
        )
        assert result2.data == {
            "username": "bob",
            "password": password,
            "scopes": ["read", "write"],
            "grant_type": "password",
        }

    await async_client_tester(
        app_oauth2_password_request_form,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_openid_connect(
    app_openid_connect: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = client.endpoint("oidc-token")
        assert result.response.request.headers["authorization"] == "Bearer oidc-token"
        # OpenIdConnect returns the full Authorization header value.
        assert result.data == "Bearer oidc-token"

        sig = signature(client.endpoint)
        assert sig.parameters["token"].annotation is str
        assert sig.parameters["token"].default is Parameter.empty

    client_tester(
        app_openid_connect, client_test, assert_format_of_generated_code=False
    )


async def test_openid_connect_async(
    app_openid_connect: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = await client.endpoint("oidc-token")
        assert result.response.request.headers["authorization"] == "Bearer oidc-token"
        # OpenIdConnect returns the full Authorization header value.
        assert result.data == "Bearer oidc-token"

        sig = signature(client.endpoint)
        assert sig.parameters["token"].annotation is str
        assert sig.parameters["token"].default is Parameter.empty

    await async_client_tester(
        app_openid_connect, client_test, assert_format_of_generated_code=False
    )


def test_shared_scheme_across_sub_deps(
    app_shared_scheme: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import signature

        result = client.endpoint("shared")
        assert result.response.request.headers["authorization"] == "Bearer shared"
        assert result.data == "a-shared|b-shared"

        sig = signature(client.endpoint)
        assert "creds" in sig.parameters
        assert len([p for p in sig.parameters if p.startswith("creds")]) == 1

    client_tester(app_shared_scheme, client_test, assert_format_of_generated_code=False)


async def test_shared_scheme_across_sub_deps_async(
    app_shared_scheme: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import signature

        result = await client.endpoint("shared")
        assert result.response.request.headers["authorization"] == "Bearer shared"
        assert result.data == "a-shared|b-shared"

        sig = signature(client.endpoint)
        assert "creds" in sig.parameters
        assert len([p for p in sig.parameters if p.startswith("creds")]) == 1

    await async_client_tester(
        app_shared_scheme, client_test, assert_format_of_generated_code=False
    )


def test_multiple_schemes(
    app_multiple_schemes: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import signature

        result = client.endpoint(creds="tok", key="k3y")
        assert result.response.request.headers["authorization"] == "Bearer tok"
        assert result.response.request.headers["x-api-key"] == "k3y"
        assert result.data == "tok|k3y"

        sig = signature(client.endpoint)
        assert "creds" in sig.parameters
        assert "key" in sig.parameters

    client_tester(
        app_multiple_schemes, client_test, assert_format_of_generated_code=False
    )


async def test_multiple_schemes_async(
    app_multiple_schemes: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import signature

        result = await client.endpoint(creds="tok", key="k3y")
        assert result.response.request.headers["authorization"] == "Bearer tok"
        assert result.response.request.headers["x-api-key"] == "k3y"
        assert result.data == "tok|k3y"

        sig = signature(client.endpoint)
        assert "creds" in sig.parameters
        assert "key" in sig.parameters

    await async_client_tester(
        app_multiple_schemes, client_test, assert_format_of_generated_code=False
    )


def test_auto_error_false_optional(
    app_auto_error_false: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result_none = client.endpoint()
        assert "authorization" not in result_none.response.request.headers
        assert result_none.data == "none"

        result = client.endpoint("maybe")
        assert result.response.request.headers["authorization"] == "Bearer maybe"
        assert result.data == "Bearer maybe"

        sig = signature(client.endpoint)
        assert sig.parameters["creds"].default is not Parameter.empty

    client_tester(
        app_auto_error_false, client_test, assert_format_of_generated_code=False
    )


async def test_auto_error_false_optional_async(
    app_auto_error_false: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result_none = await client.endpoint()
        assert "authorization" not in result_none.response.request.headers
        assert result_none.data == "none"

        result = await client.endpoint("maybe")
        assert result.response.request.headers["authorization"] == "Bearer maybe"
        assert result.data == "Bearer maybe"

        sig = signature(client.endpoint)
        assert sig.parameters["creds"].default is not Parameter.empty

    await async_client_tester(
        app_auto_error_false, client_test, assert_format_of_generated_code=False
    )


def test_implicit_scheme_on_decorator_falls_back_to_scheme_name(
    app_implicit_scheme_on_decorator: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import signature

        result = client.endpoint("dt")
        assert result.response.request.headers["authorization"] == "Bearer dt"
        assert result.data == "ok"

        sig = signature(client.endpoint)
        assert "http_bearer" in sig.parameters

    client_tester(
        app_implicit_scheme_on_decorator,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_implicit_scheme_on_decorator_falls_back_to_scheme_name_async(
    app_implicit_scheme_on_decorator: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import signature

        result = await client.endpoint("dt")
        assert result.response.request.headers["authorization"] == "Bearer dt"
        assert result.data == "ok"

        sig = signature(client.endpoint)
        assert "http_bearer" in sig.parameters

    await async_client_tester(
        app_implicit_scheme_on_decorator,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_explicit_scheme_on_decorator_falls_back_to_scheme_name(
    app_explicit_scheme_on_decorator: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import signature

        result = client.endpoint("dt")
        assert result.response.request.headers["authorization"] == "Bearer dt"
        assert result.data == "ok"

        sig = signature(client.endpoint)
        assert "decorator_bearer" in sig.parameters

    client_tester(
        app_explicit_scheme_on_decorator,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_explicit_scheme_on_decorator_falls_back_to_scheme_name_async(
    app_explicit_scheme_on_decorator: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import signature

        result = await client.endpoint("dt")
        assert result.response.request.headers["authorization"] == "Bearer dt"
        assert result.data == "ok"

        sig = signature(client.endpoint)
        assert "decorator_bearer" in sig.parameters

    await async_client_tester(
        app_explicit_scheme_on_decorator,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_invalid_security_params(
    app_invalid_security_params: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from typing import Any, cast

        import pytest

        from fastapi_typed_client import (
            FastAPIClientConflictingParamError,
            FastAPIClientError,
            FastAPIClientUnencodableParamError,
        )

        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=(
                r"^Cannot send header param `Authorization`: security scheme "
                r"`http_bearer` expects a `str`, not `int`\.$"
            ),
        ) as error:
            client.bearer(cast(Any, 123))
        assert error.value.location == "header"
        assert error.value.name == "Authorization"
        assert error.value.value == 123

        for creds, reason in (
            (
                cast(Any, ("user", "pass", "extra")),
                r"security scheme `http_basic` expects a `tuple\[str, str\]`, not `tuple`",
            ),
            (("us:er", "pass"), "HTTP Basic usernames cannot contain `:`"),
            (("üser", "pass"), "HTTP Basic credentials must be ASCII"),
        ):
            with pytest.raises(
                FastAPIClientUnencodableParamError,
                match=rf"^Cannot send header param `Authorization`: {reason}\.$",
            ):
                client.basic(creds)
        assert client.basic(("user", "pa:ss")).data == "user"

        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=(
                r"^Cannot send header param `X-API-Key`: header values must be "
                r"printable ASCII\.$"
            ),
        ) as error:
            client.api_key_header("secret\n")
        # Values might be secrets, so they must not appear in messages.
        assert "secret" not in str(error.value)
        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send cookie param `session`: cookie values cannot",
        ):
            client.api_key_cookie("a;b")

        # Header names are case-insensitive.
        with pytest.raises(
            FastAPIClientConflictingParamError,
            match=(
                r"^Cannot send header param `X-API-Key`: it is set both by a "
                r"security scheme and by another param\.$"
            ),
        ) as error:
            client.api_key_header("key", other="other")
        assert isinstance(error.value, FastAPIClientError)
        assert isinstance(error.value, ValueError)
        assert error.value.location == "header"
        assert error.value.name == "X-API-Key"
        assert client.api_key_header("key").data == "key-key"

        with pytest.raises(
            FastAPIClientConflictingParamError,
            match=r"^Cannot send cookie param `session`",
        ):
            client.api_key_cookie("key", other="other")
        with pytest.raises(
            FastAPIClientConflictingParamError,
            match=r"^Cannot send query param `api_key`",
        ):
            client.api_key_query("key", other="other")
        assert client.api_key_query("key").data == "key-key"
        with pytest.raises(
            FastAPIClientConflictingParamError,
            match=r"^Cannot send header param `authorization`",
        ):
            client.two_schemes("token", "key")

    # Unlike other tests in this file, import the errors from `fastapi_typed_client`.
    client_tester(
        app_invalid_security_params,
        client_test,
        import_client_base=True,
        assert_format_of_generated_code=False,
    )


async def test_invalid_security_params_async(
    app_invalid_security_params: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from typing import Any, cast

        import pytest

        from fastapi_typed_client import (
            FastAPIClientConflictingParamError,
            FastAPIClientError,
            FastAPIClientUnencodableParamError,
        )

        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=(
                r"^Cannot send header param `Authorization`: security scheme "
                r"`http_bearer` expects a `str`, not `int`\.$"
            ),
        ) as error:
            await client.bearer(cast(Any, 123))
        assert error.value.location == "header"
        assert error.value.name == "Authorization"
        assert error.value.value == 123

        for creds, reason in (
            (
                cast(Any, ("user", "pass", "extra")),
                r"security scheme `http_basic` expects a `tuple\[str, str\]`, not `tuple`",
            ),
            (("us:er", "pass"), "HTTP Basic usernames cannot contain `:`"),
            (("üser", "pass"), "HTTP Basic credentials must be ASCII"),
        ):
            with pytest.raises(
                FastAPIClientUnencodableParamError,
                match=rf"^Cannot send header param `Authorization`: {reason}\.$",
            ):
                await client.basic(creds)
        assert (await client.basic(("user", "pa:ss"))).data == "user"

        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=(
                r"^Cannot send header param `X-API-Key`: header values must be "
                r"printable ASCII\.$"
            ),
        ) as error:
            await client.api_key_header("secret\n")
        # Values might be secrets, so they must not appear in messages.
        assert "secret" not in str(error.value)
        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send cookie param `session`: cookie values cannot",
        ):
            await client.api_key_cookie("a;b")

        # Header names are case-insensitive.
        with pytest.raises(
            FastAPIClientConflictingParamError,
            match=(
                r"^Cannot send header param `X-API-Key`: it is set both by a "
                r"security scheme and by another param\.$"
            ),
        ) as error:
            await client.api_key_header("key", other="other")
        assert isinstance(error.value, FastAPIClientError)
        assert isinstance(error.value, ValueError)
        assert error.value.location == "header"
        assert error.value.name == "X-API-Key"
        assert (await client.api_key_header("key")).data == "key-key"

        with pytest.raises(
            FastAPIClientConflictingParamError,
            match=r"^Cannot send cookie param `session`",
        ):
            await client.api_key_cookie("key", other="other")
        with pytest.raises(
            FastAPIClientConflictingParamError,
            match=r"^Cannot send query param `api_key`",
        ):
            await client.api_key_query("key", other="other")
        assert (await client.api_key_query("key")).data == "key-key"
        with pytest.raises(
            FastAPIClientConflictingParamError,
            match=r"^Cannot send header param `authorization`",
        ):
            await client.two_schemes("token", "key")

    # Unlike other tests in this file, import the errors from `fastapi_typed_client`.
    await async_client_tester(
        app_invalid_security_params,
        client_test,
        import_client_base=True,
        assert_format_of_generated_code=False,
    )
