from typing import Annotated, Any
from uuid import UUID

import pytest
from fastapi import Body, Cookie, Depends, FastAPI, Header, Path, Query

from ..client_tester import AsyncClientTester, ClientTester
from ..shared import TextAndNum

type _PathParam = Annotated[int, Path()]
type _QueryParam = Annotated[str, Query()]
type _HeaderParam = Annotated[str, Header(alias="X-Param")]
type _CookieParam = Annotated[UUID, Cookie()]
type _BodyParam = Annotated[TextAndNum, Body()]
type _EmbeddedBodyParam = Annotated[TextAndNum, Body(embed=True)]


def _path_dep_a(param: _PathParam) -> str:
    return f"path-a-{param}"


def _path_dep_b(param: _PathParam) -> str:
    return f"path-b-{param}"


def _path_dep_c(param: _PathParam) -> str:
    return f"path-c-{param}"


def _query_dep_a(param: _QueryParam) -> str:
    return f"query-a-{param}"


def _query_dep_b(param: Annotated[str, Query()] = "default") -> str:
    return f"query-b-{param}"


def _header_dep_a(param: _HeaderParam) -> str:
    return f"header-a-{param}"


def _header_dep_b(param: Annotated[str, Header(alias="X-Param")] = "fallback") -> str:
    return f"header-b-{param}"


def _cookie_dep_a(param: _CookieParam) -> str:
    return f"cookie-a-{param}"


def _cookie_dep_b(param: _CookieParam) -> str:
    return f"cookie-b-{param}"


def _unembedded_body_dep_a(param: _BodyParam) -> str:
    return f"unembedded-a-{param.text}-{param.num}"


def _unembedded_body_dep_b(param: _BodyParam) -> str:
    return f"unembedded-b-{param.text}-{param.num}"


def _embedded_body_dep_a(param: _EmbeddedBodyParam) -> str:
    return f"embedded-a-{param.text}-{param.num}"


def _embedded_body_dep_b(param: _EmbeddedBodyParam) -> str:
    return f"embedded-b-{param.text}-{param.num}"


type _PathDepA = Annotated[str, Depends(_path_dep_a)]
type _PathDepB = Annotated[str, Depends(_path_dep_b)]
type _PathDepC = Annotated[str, Depends(_path_dep_c)]
type _QueryDepA = Annotated[str, Depends(_query_dep_a)]
type _QueryDepB = Annotated[str, Depends(_query_dep_b)]
type _HeaderDepA = Annotated[str, Depends(_header_dep_a)]
type _HeaderDepB = Annotated[str, Depends(_header_dep_b)]
type _CookieDepA = Annotated[str, Depends(_cookie_dep_a)]
type _CookieDepB = Annotated[str, Depends(_cookie_dep_b)]
type _UnembeddedBodyDepA = Annotated[str, Depends(_unembedded_body_dep_a)]
type _UnembeddedBodyDepB = Annotated[str, Depends(_unembedded_body_dep_b)]
type _EmbeddedBodyDepA = Annotated[str, Depends(_embedded_body_dep_a)]
type _EmbeddedBodyDepB = Annotated[str, Depends(_embedded_body_dep_b)]


@pytest.fixture
def app_with_shared_dep_path_params() -> FastAPI:
    app = FastAPI()

    @app.get("/path/{param}")  # noqa: FAST003
    def path_two_deps(a: _PathDepA, b: _PathDepB) -> str:
        return f"{a}|{b}"

    @app.get("/path-three/{param}")  # noqa: FAST003
    def path_three_deps(a: _PathDepA, b: _PathDepB, c: _PathDepC) -> str:
        return f"{a}|{b}|{c}"

    @app.get("/path-endpoint/{param}")
    def path_endpoint_and_dep(param: _PathParam, a: _PathDepA) -> str:
        return f"{param}|{a}"

    return app


@pytest.fixture
def app_with_shared_dep_query_param() -> FastAPI:
    app = FastAPI()

    @app.get("/query")
    def query_two_deps(a: _QueryDepA, b: _QueryDepB) -> str:
        return f"{a}|{b}"

    return app


@pytest.fixture
def app_with_shared_dep_header_param() -> FastAPI:
    app = FastAPI()

    @app.get("/header")
    def header_two_deps(a: _HeaderDepA, b: _HeaderDepB) -> str:
        return f"{a}|{b}"

    return app


@pytest.fixture
def app_with_shared_dep_cookie_param() -> FastAPI:
    app = FastAPI()

    @app.get("/cookie")
    def cookie_two_deps(a: _CookieDepA, b: _CookieDepB) -> str:
        return f"{a}|{b}"

    return app


@pytest.fixture
def app_with_shared_dep_body_params() -> FastAPI:
    app = FastAPI()

    @app.post("/unembedded-body")
    def unembedded_body_two_deps(a: _UnembeddedBodyDepA, b: _UnembeddedBodyDepB) -> str:
        return f"{a}|{b}"

    @app.post("/embedded-body")
    def embedded_body_two_deps(
        a: _EmbeddedBodyDepA,
        b: _EmbeddedBodyDepB,
        param2: Annotated[TextAndNum, Body(embed=True)],
    ) -> str:
        return f"{a}|{b}|{param2.text}-{param2.num}"

    @app.post("/mixed-body-unembedded-first")
    def mixed_body_two_deps_unembedded_first(
        a: _UnembeddedBodyDepA, b: _EmbeddedBodyDepA
    ) -> str:
        return f"{a}|{b}"

    @app.post("/mixed-body-embedded-first")
    def mixed_body_two_deps_embedded_first(
        a: _EmbeddedBodyDepA, b: _UnembeddedBodyDepA
    ) -> str:
        return f"{a}|{b}"

    return app


def test_shared_path_param_across_sub_dependencies(
    app_with_shared_dep_path_params: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        assert client.path_two_deps(param=42).data == "path-a-42|path-b-42"
        assert client.path_three_deps(param=7).data == "path-a-7|path-b-7|path-c-7"
        assert client.path_endpoint_and_dep(param=13).data == "13|path-a-13"

        for endpoint in (
            client.path_two_deps,
            client.path_three_deps,
            client.path_endpoint_and_dep,
        ):
            endpoint_signature = signature(endpoint)
            assert list(endpoint_signature.parameters) == [
                "param",
                "raise_if_not_default_status",
                "client_exts",
            ]
            assert endpoint_signature.parameters["param"].default is Parameter.empty
            assert endpoint_signature.parameters["param"].annotation is int

    client_tester(
        app_with_shared_dep_path_params,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_shared_path_param_across_sub_dependencies_async(
    app_with_shared_dep_path_params: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        assert (await client.path_two_deps(param=42)).data == "path-a-42|path-b-42"
        assert (
            await client.path_three_deps(param=7)
        ).data == "path-a-7|path-b-7|path-c-7"
        assert (await client.path_endpoint_and_dep(param=13)).data == "13|path-a-13"

        for endpoint in (
            client.path_two_deps,
            client.path_three_deps,
            client.path_endpoint_and_dep,
        ):
            endpoint_signature = signature(endpoint)
            assert list(endpoint_signature.parameters) == [
                "param",
                "raise_if_not_default_status",
                "client_exts",
            ]
            assert endpoint_signature.parameters["param"].default is Parameter.empty
            assert endpoint_signature.parameters["param"].annotation is int

    await async_client_tester(
        app_with_shared_dep_path_params,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_shared_query_param_across_sub_dependencies(
    app_with_shared_dep_query_param: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = client.query_two_deps(param="hello")
        assert result.response.url.params.get("param") == "hello"
        assert result.data == "query-a-hello|query-b-hello"

        sig = signature(client.query_two_deps)
        # One dep declares `param` as required, the other as optional with a
        # default. The merged parameter must be required.
        assert sig.parameters["param"].default is Parameter.empty
        assert sig.parameters["param"].annotation is str

    client_tester(
        app_with_shared_dep_query_param,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_shared_query_param_across_sub_dependencies_async(
    app_with_shared_dep_query_param: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = await client.query_two_deps(param="hello")
        assert result.response.url.params.get("param") == "hello"
        assert result.data == "query-a-hello|query-b-hello"

        sig = signature(client.query_two_deps)
        # One dep declares `param` as required, the other as optional with a
        # default. The merged parameter must be required.
        assert sig.parameters["param"].default is Parameter.empty
        assert sig.parameters["param"].annotation is str

    await async_client_tester(
        app_with_shared_dep_query_param,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_shared_header_param_across_sub_dependencies(
    app_with_shared_dep_header_param: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = client.header_two_deps(param="hi")
        assert result.response.request.headers["X-Param"] == "hi"
        assert result.data == "header-a-hi|header-b-hi"

        sig = signature(client.header_two_deps)
        # Both deps use the same alias (X-Param); the merged parameter must be
        # required since one dep declares it as required.
        assert sig.parameters["param"].default is Parameter.empty
        assert sig.parameters["param"].annotation is str

    client_tester(
        app_with_shared_dep_header_param,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_shared_header_param_across_sub_dependencies_async(
    app_with_shared_dep_header_param: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from inspect import Parameter, signature

        result = await client.header_two_deps(param="hi")
        assert result.response.request.headers["X-Param"] == "hi"
        assert result.data == "header-a-hi|header-b-hi"

        sig = signature(client.header_two_deps)
        # Both deps use the same alias (X-Param); the merged parameter must be
        # required since one dep declares it as required.
        assert sig.parameters["param"].default is Parameter.empty
        assert sig.parameters["param"].annotation is str

    await async_client_tester(
        app_with_shared_dep_header_param,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_shared_cookie_param_across_sub_dependencies(
    app_with_shared_dep_cookie_param: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from uuid import uuid4

        import pytest

        param = uuid4()
        with (
            pytest.warns(UserWarning, match="cookie parameter"),
            pytest.warns(DeprecationWarning, match="per-request cookie"),
        ):
            result = client.cookie_two_deps(param=param)
        assert result.response.request.headers["cookie"] == f"param={param}"
        assert result.data == f"cookie-a-{param}|cookie-b-{param}"

    client_tester(
        app_with_shared_dep_cookie_param,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_shared_cookie_param_across_sub_dependencies_async(
    app_with_shared_dep_cookie_param: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from uuid import uuid4

        import pytest

        param = uuid4()
        with (
            pytest.warns(UserWarning, match="cookie parameter"),
            pytest.warns(DeprecationWarning, match="per-request cookie"),
        ):
            result = await client.cookie_two_deps(param=param)
        assert result.response.request.headers["cookie"] == f"param={param}"
        assert result.data == f"cookie-a-{param}|cookie-b-{param}"

    await async_client_tester(
        app_with_shared_dep_cookie_param,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_shared_body_param_unembedded(
    app_with_shared_dep_body_params: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum  # type: ignore[client_tester_only]

        result = client.unembedded_body_two_deps(TextAndNum(text="aaa", num=1))
        assert result.response.request.content == b'{"text":"aaa","num":1}'
        assert result.data == "unembedded-a-aaa-1|unembedded-b-aaa-1"

    client_tester(
        app_with_shared_dep_body_params,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_shared_body_param_unembedded_async(
    app_with_shared_dep_body_params: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum  # type: ignore[client_tester_only]

        result = await client.unembedded_body_two_deps(TextAndNum(text="aaa", num=1))
        assert result.response.request.content == b'{"text":"aaa","num":1}'
        assert result.data == "unembedded-a-aaa-1|unembedded-b-aaa-1"

    await async_client_tester(
        app_with_shared_dep_body_params,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_shared_body_param_embedded(
    app_with_shared_dep_body_params: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum  # type: ignore[client_tester_only]

        result = client.embedded_body_two_deps(
            param=TextAndNum(text="aaa", num=1), param2=TextAndNum(text="bbb", num=2)
        )
        assert (
            result.response.request.content
            == b'{"param":{"text":"aaa","num":1},"param2":{"text":"bbb","num":2}}'
        )
        assert result.data == "embedded-a-aaa-1|embedded-b-aaa-1|bbb-2"

    client_tester(
        app_with_shared_dep_body_params,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_shared_body_param_embedded_async(
    app_with_shared_dep_body_params: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum  # type: ignore[client_tester_only]

        result = await client.embedded_body_two_deps(
            param=TextAndNum(text="aaa", num=1), param2=TextAndNum(text="bbb", num=2)
        )
        assert (
            result.response.request.content
            == b'{"param":{"text":"aaa","num":1},"param2":{"text":"bbb","num":2}}'
        )
        assert result.data == "embedded-a-aaa-1|embedded-b-aaa-1|bbb-2"

    await async_client_tester(
        app_with_shared_dep_body_params,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_shared_body_param_mixed_embed_unembedded_first(
    app_with_shared_dep_body_params: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum  # type: ignore[client_tester_only]

        # One dep declares the body via `Body()` and the other via
        # `Body(embed=True)`. They share the same Python name `param` and the
        # same annotation, so they collapse to a single client parameter.
        # FastAPI picks up the embed flag from the *first* body param in its
        # flattened body_params list — the `Body()` (unembedded) dep comes
        # first here, so the route ends up unembedded and the wire body is
        # the raw model.
        result = client.mixed_body_two_deps_unembedded_first(
            param=TextAndNum(text="aaa", num=1)
        )
        assert result.response.request.content == b'{"text":"aaa","num":1}'
        assert result.data == "unembedded-a-aaa-1|embedded-a-aaa-1"

    client_tester(
        app_with_shared_dep_body_params,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_shared_body_param_mixed_embed_unembedded_first_async(
    app_with_shared_dep_body_params: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum  # type: ignore[client_tester_only]

        # One dep declares the body via `Body()` and the other via
        # `Body(embed=True)`. They share the same Python name `param` and the
        # same annotation, so they collapse to a single client parameter.
        # FastAPI picks up the embed flag from the *first* body param in its
        # flattened body_params list — the `Body()` (unembedded) dep comes
        # first here, so the route ends up unembedded and the wire body is
        # the raw model.
        result = await client.mixed_body_two_deps_unembedded_first(
            param=TextAndNum(text="aaa", num=1)
        )
        assert result.response.request.content == b'{"text":"aaa","num":1}'
        assert result.data == "unembedded-a-aaa-1|embedded-a-aaa-1"

    await async_client_tester(
        app_with_shared_dep_body_params,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_shared_body_param_mixed_embed_embedded_first(
    app_with_shared_dep_body_params: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum  # type: ignore[client_tester_only]

        # Swapping the dep order flips FastAPI's embed decision: the
        # `Body(embed=True)` dep comes first, so the route is embedded and
        # the wire body wraps the model in `{"param": …}`.
        result = client.mixed_body_two_deps_embedded_first(
            param=TextAndNum(text="aaa", num=1)
        )
        assert result.response.request.content == b'{"param":{"text":"aaa","num":1}}'
        assert result.data == "embedded-a-aaa-1|unembedded-a-aaa-1"

    client_tester(
        app_with_shared_dep_body_params,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_shared_body_param_mixed_embed_embedded_first_async(
    app_with_shared_dep_body_params: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from ..shared import TextAndNum  # type: ignore[client_tester_only]

        # Swapping the dep order flips FastAPI's embed decision: the
        # `Body(embed=True)` dep comes first, so the route is embedded and
        # the wire body wraps the model in `{"param": …}`.
        result = await client.mixed_body_two_deps_embedded_first(
            param=TextAndNum(text="aaa", num=1)
        )
        assert result.response.request.content == b'{"param":{"text":"aaa","num":1}}'
        assert result.data == "embedded-a-aaa-1|unembedded-a-aaa-1"

    await async_client_tester(
        app_with_shared_dep_body_params,
        client_test,
        assert_format_of_generated_code=False,
    )
