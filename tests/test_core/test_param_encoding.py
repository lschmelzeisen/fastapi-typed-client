from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import UUID

import pytest
from fastapi import Cookie, Depends, FastAPI, Header, Query
from pydantic import BaseModel, BeforeValidator, Field, SecretBytes, SecretStr

from fastapi_typed_client import generate_fastapi_typed_client

from ..client_tester import AsyncClientTester, ClientTester
from ..shared import FooBarEnum

# Tests in this file set `assert_format_of_generated_code=False`, since all routes have
# multiple responses (see test_multiple_responses.py). Tests importing errors from
# `fastapi_typed_client` set `import_client_base=True`, and those also importing from
# `shared` set `assert_sorting_of_imports=False`, since `shared` becomes first-party in
# the generated test file.


class _HeaderModel(BaseModel):
    x_val: int
    y_val: int = Field(default=0, alias="Y-Explicit")
    z_val: int = Field(default=0, validation_alias="Z-VA")


class _Sentinel:
    __slots__ = ()


def _data_dependent_default(data: dict[str, int]) -> int:
    return data["a"]


class _DataDependentDefaultModel(BaseModel):
    a: int = 1
    b: int = Field(default_factory=_data_dependent_default)


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/header")
    def header(
        revision: Annotated[
            Literal[1], BeforeValidator(int), Header(alias="Api-Revision")
        ],
        i: Annotated[int, Header()],
        b: Annotated[bool, Header()],
        f: Annotated[float, Header()],
        e: Annotated[FooBarEnum, Header()],
        items: Annotated[list[int], Header()],
        s: Annotated[str, Header()] = "",
    ) -> str:
        return repr((revision, i, b, f, e, items, s))

    @app.get("/header-values")
    def header_values(
        u: Annotated[UUID, Header()],
        d: Annotated[datetime, Header()],
        t: Annotated[timedelta, Header()],
        dec: Annotated[Decimal, Header()],
        secret: Annotated[SecretStr, Header()],
        secret_bytes: Annotated[SecretBytes, Header()],
        raw: Annotated[bytes, Header()] = b"",
    ) -> str:
        return (
            f"{u} {d.isoformat()} {t} {dec} {secret.get_secret_value()} "
            f"{secret_bytes.get_secret_value()!r} {raw!r}"
        )

    @app.get("/cookie")
    def cookie(
        i: Annotated[int, Cookie()],
        b: Annotated[bool, Cookie()],
        f: Annotated[float, Cookie()],
        s: Annotated[str, Cookie()] = "",
    ) -> str:
        return repr((i, b, f, s))

    @app.get("/query")
    def query(
        b: bool,
        f: float,
        items: Annotated[list[int], Query()],
        dec: Decimal = Decimal(0),
        t: timedelta = timedelta(0),
    ) -> str:
        return repr((b, f, items, dec, t))

    @app.get("/path/{b}/{f}/{s}")
    def path(b: bool, f: float, s: str) -> str:
        return repr((b, f, s))

    @app.get("/path-values/{dec}/{t}")
    def path_values(dec: Decimal, t: timedelta) -> str:
        return repr((dec, t))

    @app.get("/path-converter/{s:path}")
    def path_converter(s: str) -> str:
        return s

    return app


@pytest.fixture
def app_with_aliases() -> FastAPI:
    app = FastAPI()

    @app.get("/aliases")
    def aliases(
        va: Annotated[str, Query(validation_alias="vaAlias")],
        h_va: Annotated[str, Header(validation_alias="X-VA")],
        no_conv: Annotated[str, Header(convert_underscores=False)],
    ) -> str:
        return repr((va, h_va, no_conv))

    @app.get("/header-model")
    def header_model(model: Annotated[_HeaderModel, Header()]) -> str:
        return repr((model.x_val, model.y_val, model.z_val))

    @app.get("/header-model-unconverted")
    def header_model_unconverted(
        model: Annotated[_HeaderModel, Header(convert_underscores=False)],
    ) -> str:
        return repr((model.x_val, model.y_val, model.z_val))

    return app


@pytest.fixture
def app_with_unencodable_defaults() -> FastAPI:
    app = FastAPI()

    @app.get("/defaults")
    def defaults(
        *,
        q_required: Annotated[int | None, Query()],
        q_none: int | None = None,
        q_five: int | None = 5,
        q_empty: Annotated[list[int], Query(default_factory=list)],
        q_list_none: Annotated[list[int] | None, Query()] = None,
        h_none: Annotated[int | None, Header()] = None,
        h_five: Annotated[int | None, Header()] = 5,
        h_empty: Annotated[list[int], Header(default_factory=list)],
        c_none: Annotated[int | None, Cookie()] = None,
        c_five: Annotated[int | None, Cookie()] = 5,
    ) -> str:
        return repr(
            (
                q_required,
                q_none,
                q_five,
                q_empty,
                q_list_none,
                h_none,
                h_five,
                h_empty,
                c_none,
                c_five,
            )
        )

    @app.get("/path/{p}")
    def path(p: int | None) -> str:
        return repr(p)

    def dep_none(x: int | None = None) -> int | None:
        return x

    def dep_five(x: int | None = 5) -> int | None:
        return x

    @app.get("/ambiguous")
    def ambiguous(
        x1: Annotated[int | None, Depends(dep_none)],
        x2: Annotated[int | None, Depends(dep_five)],
    ) -> str:
        return repr((x1, x2))

    return app


def test_non_str_values(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal
        from uuid import UUID

        import pytest
        from pydantic import SecretBytes, SecretStr

        from ..shared import FooBarEnum

        result = client.header(
            revision=1, i=1, b=True, f=1.5, e=FooBarEnum.FOO, items=[1, 2], s="a\tb"
        )
        assert (
            result.data == "(1, 1, True, 1.5, <FooBarEnum.FOO: 123>, [1, 2], 'a\\tb')"
        )
        headers = result.response.request.headers
        assert headers["Api-Revision"] == "1"
        assert headers["b"] == "true"
        assert headers["e"] == "123"
        assert headers.get_list("items") == ["1", "2"]

        uuid = UUID("12345678-1234-5678-1234-567812345678")
        result = client.header_values(
            u=uuid,
            d=datetime(2026, 10, 3, 12, tzinfo=UTC),
            t=timedelta(hours=1),
            dec=Decimal("12345678901234567890.123"),
            secret=SecretStr("secret"),
            secret_bytes=SecretBytes(b"bytes"),
            raw=b"raw",
        )
        assert result.data == (
            f"{uuid} 2026-10-03T12:00:00+00:00 1:00:00 12345678901234567890.123 secret "
            "b'bytes' b'raw'"
        )
        assert result.response.request.headers["t"] == "PT1H"

        with pytest.warns(DeprecationWarning, match="per-request cookie"):
            result = client.cookie(i=1, b=False, f=1e-25, s='"')
        assert result.data == "(1, False, 1e-25, '\"')"
        assert result.response.request.headers["cookie"] == 'b=false; f=1e-25; i=1; s="'

        result = client.query(
            b=True, f=1e-25, items=[1, 2], dec=Decimal("1.10"), t=timedelta(seconds=-1)
        )
        assert result.data == (
            "(True, 1e-25, [1, 2], Decimal('1.10'), "
            "datetime.timedelta(days=-1, seconds=86399))"
        )
        assert (
            result.response.url.query
            == b"b=true&f=1e-25&items=1&items=2&dec=1.10&t=-PT1S"
        )

        # Starlette's `TestClient` and httpx2's `ASGITransport` percent-decode paths twice,
        # so values can't contain `%XX`.
        result = client.path(b=False, f=1e-25, s="a?b#c%")
        assert result.data == "(False, 1e-25, 'a?b#c%')"
        assert result.response.url.raw_path == b"/path/false/1e-25/a%3Fb%23c%25"
        result = client.path_values(dec=Decimal("1E+2"), t=timedelta(hours=1))
        assert result.data == "(Decimal('1E+2'), datetime.timedelta(seconds=3600))"
        assert result.response.url.raw_path == b"/path-values/1E%2B2/PT1H"
        result = client.path_converter("a/b c")
        assert result.data == "a/b c"

    client_tester(
        app,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_non_str_values_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal
        from uuid import UUID

        import pytest
        from pydantic import SecretBytes, SecretStr

        from ..shared import FooBarEnum

        result = await client.header(
            revision=1, i=1, b=True, f=1.5, e=FooBarEnum.FOO, items=[1, 2], s="a\tb"
        )
        assert (
            result.data == "(1, 1, True, 1.5, <FooBarEnum.FOO: 123>, [1, 2], 'a\\tb')"
        )
        headers = result.response.request.headers
        assert headers["Api-Revision"] == "1"
        assert headers["b"] == "true"
        assert headers["e"] == "123"
        assert headers.get_list("items") == ["1", "2"]

        uuid = UUID("12345678-1234-5678-1234-567812345678")
        result = await client.header_values(
            u=uuid,
            d=datetime(2026, 10, 3, 12, tzinfo=UTC),
            t=timedelta(hours=1),
            dec=Decimal("12345678901234567890.123"),
            secret=SecretStr("secret"),
            secret_bytes=SecretBytes(b"bytes"),
            raw=b"raw",
        )
        assert result.data == (
            f"{uuid} 2026-10-03T12:00:00+00:00 1:00:00 12345678901234567890.123 secret "
            "b'bytes' b'raw'"
        )
        assert result.response.request.headers["t"] == "PT1H"

        with pytest.warns(DeprecationWarning, match="per-request cookie"):
            result = await client.cookie(i=1, b=False, f=1e-25, s='"')
        assert result.data == "(1, False, 1e-25, '\"')"
        assert result.response.request.headers["cookie"] == 'b=false; f=1e-25; i=1; s="'

        result = await client.query(
            b=True, f=1e-25, items=[1, 2], dec=Decimal("1.10"), t=timedelta(seconds=-1)
        )
        assert result.data == (
            "(True, 1e-25, [1, 2], Decimal('1.10'), "
            "datetime.timedelta(days=-1, seconds=86399))"
        )
        assert (
            result.response.url.query
            == b"b=true&f=1e-25&items=1&items=2&dec=1.10&t=-PT1S"
        )

        # Starlette's `TestClient` and httpx2's `ASGITransport` percent-decode paths twice,
        # so values can't contain `%XX`.
        result = await client.path(b=False, f=1e-25, s="a?b#c%")
        assert result.data == "(False, 1e-25, 'a?b#c%')"
        assert result.response.url.raw_path == b"/path/false/1e-25/a%3Fb%23c%25"
        result = await client.path_values(dec=Decimal("1E+2"), t=timedelta(hours=1))
        assert result.data == "(Decimal('1E+2'), datetime.timedelta(seconds=3600))"
        assert result.response.url.raw_path == b"/path-values/1E%2B2/PT1H"
        result = await client.path_converter("a/b c")
        assert result.data == "a/b c"

    await async_client_tester(
        app,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_aliases(app_with_aliases: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        result = client.aliases(va="a", h_va="b", no_conv="c")
        assert result.data == "('a', 'b', 'c')"
        assert result.response.url.query == b"vaAlias=a"
        assert result.response.request.headers["X-VA"] == "b"
        assert result.response.request.headers["no_conv"] == "c"

        result = client.header_model(x_val=1, y_val=2, z_val=3)
        assert result.data == "(1, 2, 3)"
        headers = result.response.request.headers
        assert (headers["x-val"], headers["Y-Explicit"], headers["Z-VA"]) == (
            "1",
            "2",
            "3",
        )

        result = client.header_model_unconverted(x_val=1)
        assert result.data == "(1, 0, 0)"
        assert result.response.request.headers["x_val"] == "1"

    client_tester(
        app_with_aliases,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_aliases_async(
    app_with_aliases: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        result = await client.aliases(va="a", h_va="b", no_conv="c")
        assert result.data == "('a', 'b', 'c')"
        assert result.response.url.query == b"vaAlias=a"
        assert result.response.request.headers["X-VA"] == "b"
        assert result.response.request.headers["no_conv"] == "c"

        result = await client.header_model(x_val=1, y_val=2, z_val=3)
        assert result.data == "(1, 2, 3)"
        headers = result.response.request.headers
        assert (headers["x-val"], headers["Y-Explicit"], headers["Z-VA"]) == (
            "1",
            "2",
            "3",
        )

        result = await client.header_model_unconverted(x_val=1)
        assert result.data == "(1, 0, 0)"
        assert result.response.request.headers["x_val"] == "1"

    await async_client_tester(
        app_with_aliases,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_unencodable_values(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal
        from typing import Any, cast
        from uuid import UUID

        import pytest
        from pydantic import SecretBytes, SecretStr

        from fastapi_typed_client import (
            FastAPIClientError,
            FastAPIClientUnencodableParamError,
        )

        from ..shared import FooBarEnum

        header_kwargs: dict[str, Any] = {
            "revision": 1,
            "i": 1,
            "b": True,
            "f": 1.5,
            "e": FooBarEnum.FOO,
        }
        for items, type_name in (([1, None], "NoneType"), ([[1]], "list")):
            with pytest.raises(
                FastAPIClientUnencodableParamError,
                match=rf"^Cannot send header param `items`: values of type `{type_name}`",
            ):
                client.header(**header_kwargs, items=cast(Any, items))
        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send header param `s`: header values must be printable ASCII\.$",
        ) as error:
            client.header(**header_kwargs, items=[1], s="secret\r\n")
        assert isinstance(error.value, FastAPIClientError)
        assert isinstance(error.value, ValueError)
        assert error.value.location == "header"
        assert error.value.name == "s"
        assert error.value.value == "secret\r\n"
        # Values might be secrets, so they must not appear in messages.
        assert "secret" not in str(error.value)
        for s, reason in (
            ("ä", "must be printable ASCII"),
            (" a", "cannot have leading or trailing whitespace"),
        ):
            with pytest.raises(
                FastAPIClientUnencodableParamError,
                match=rf"^Cannot send header param `s`: header values {reason}\.$",
            ):
                client.header(**header_kwargs, items=[1], s=s)

        header_values_kwargs: dict[str, Any] = {
            "u": UUID(int=0),
            "d": datetime(2026, 10, 3, tzinfo=UTC),
            "t": timedelta(0),
            "dec": Decimal(0),
            "secret": SecretStr("secret"),
            "secret_bytes": SecretBytes(b"bytes"),
        }
        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send header param `raw`: values of type `bytes` cannot",
        ):
            cast(Any, client).header_values(**header_values_kwargs, raw=b"\xff")
        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send header param `secret-bytes`: values of type `SecretBytes`",
        ):
            cast(Any, client).header_values(
                **(header_values_kwargs | {"secret_bytes": SecretBytes(b"\xff")})
            )

        for s, reason in (
            ("a;b", "cannot contain `;` or be enclosed in double quotes"),
            ('"a"', "cannot contain `;` or be enclosed in double quotes"),
            ("ä", "must be printable ASCII"),
        ):
            with pytest.raises(
                FastAPIClientUnencodableParamError,
                match=rf"^Cannot send cookie param `s`: cookie values {reason}\.$",
            ):
                client.cookie(i=1, b=True, f=1.5, s=s)
        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send cookie param `i`: values of type `list`",
        ):
            client.cookie(i=cast(Any, [1]), b=True, f=1.5)

        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send query param `f`: values of type `dict`",
        ):
            client.query(b=True, f=cast(Any, {"a": 1}), items=[])

        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send path param `s`: values of type `list`",
        ):
            client.path(b=True, f=1.5, s=cast(Any, ["a"]))
        for s, reason in (
            ("..", r"cannot contain `\.` or `\.\.` segments"),
            (".", r"cannot contain `\.` or `\.\.` segments"),
        ):
            with pytest.raises(
                FastAPIClientUnencodableParamError,
                match=rf"^Cannot send path param `s`: path values {reason}\.$",
            ):
                client.path(b=True, f=1.5, s=s)
        with pytest.raises(
            FastAPIClientUnencodableParamError, match=r"`\.` or `\.\.` segments"
        ):
            client.path_converter("a/../b")

    client_tester(
        app,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


async def test_unencodable_values_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from datetime import UTC, datetime, timedelta
        from decimal import Decimal
        from typing import Any, cast
        from uuid import UUID

        import pytest
        from pydantic import SecretBytes, SecretStr

        from fastapi_typed_client import (
            FastAPIClientError,
            FastAPIClientUnencodableParamError,
        )

        from ..shared import FooBarEnum

        header_kwargs: dict[str, Any] = {
            "revision": 1,
            "i": 1,
            "b": True,
            "f": 1.5,
            "e": FooBarEnum.FOO,
        }
        for items, type_name in (([1, None], "NoneType"), ([[1]], "list")):
            with pytest.raises(
                FastAPIClientUnencodableParamError,
                match=rf"^Cannot send header param `items`: values of type `{type_name}`",
            ):
                await client.header(**header_kwargs, items=cast(Any, items))
        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send header param `s`: header values must be printable ASCII\.$",
        ) as error:
            await client.header(**header_kwargs, items=[1], s="secret\r\n")
        assert isinstance(error.value, FastAPIClientError)
        assert isinstance(error.value, ValueError)
        assert error.value.location == "header"
        assert error.value.name == "s"
        assert error.value.value == "secret\r\n"
        # Values might be secrets, so they must not appear in messages.
        assert "secret" not in str(error.value)
        for s, reason in (
            ("ä", "must be printable ASCII"),
            (" a", "cannot have leading or trailing whitespace"),
        ):
            with pytest.raises(
                FastAPIClientUnencodableParamError,
                match=rf"^Cannot send header param `s`: header values {reason}\.$",
            ):
                await client.header(**header_kwargs, items=[1], s=s)

        header_values_kwargs: dict[str, Any] = {
            "u": UUID(int=0),
            "d": datetime(2026, 10, 3, tzinfo=UTC),
            "t": timedelta(0),
            "dec": Decimal(0),
            "secret": SecretStr("secret"),
            "secret_bytes": SecretBytes(b"bytes"),
        }
        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send header param `raw`: values of type `bytes` cannot",
        ):
            await cast(Any, client).header_values(**header_values_kwargs, raw=b"\xff")
        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send header param `secret-bytes`: values of type `SecretBytes`",
        ):
            await cast(Any, client).header_values(
                **(header_values_kwargs | {"secret_bytes": SecretBytes(b"\xff")})
            )

        for s, reason in (
            ("a;b", "cannot contain `;` or be enclosed in double quotes"),
            ('"a"', "cannot contain `;` or be enclosed in double quotes"),
            ("ä", "must be printable ASCII"),
        ):
            with pytest.raises(
                FastAPIClientUnencodableParamError,
                match=rf"^Cannot send cookie param `s`: cookie values {reason}\.$",
            ):
                await client.cookie(i=1, b=True, f=1.5, s=s)
        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send cookie param `i`: values of type `list`",
        ):
            await client.cookie(i=cast(Any, [1]), b=True, f=1.5)

        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send query param `f`: values of type `dict`",
        ):
            await client.query(b=True, f=cast(Any, {"a": 1}), items=[])

        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=r"^Cannot send path param `s`: values of type `list`",
        ):
            await client.path(b=True, f=1.5, s=cast(Any, ["a"]))
        for s, reason in (
            ("..", r"cannot contain `\.` or `\.\.` segments"),
            (".", r"cannot contain `\.` or `\.\.` segments"),
        ):
            with pytest.raises(
                FastAPIClientUnencodableParamError,
                match=rf"^Cannot send path param `s`: path values {reason}\.$",
            ):
                await client.path(b=True, f=1.5, s=s)
        with pytest.raises(
            FastAPIClientUnencodableParamError, match=r"`\.` or `\.\.` segments"
        ):
            await client.path_converter("a/../b")

    await async_client_tester(
        app,
        client_test,
        import_client_base=True,
        assert_sorting_of_imports=False,
        assert_format_of_generated_code=False,
    )


def test_unencodable_values_renamed(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        import sys

        import pytest

        from ..shared import FooBarEnum

        module = vars(sys.modules[type(client).__module__])

        with pytest.raises(ValueError, match=r"^Cannot send header param `s`") as error:
            client.header(
                revision=1, i=1, b=True, f=1.5, e=FooBarEnum.FOO, items=[1], s="ä"
            )
        assert type(error.value) is module["TestClientUnencodableParamError"]
        assert isinstance(error.value, module["TestClientError"])

    client_tester(
        app,
        client_test,
        assert_format_of_generated_code=False,
    )


async def test_unencodable_values_renamed_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        import sys

        import pytest

        from ..shared import FooBarEnum

        module = vars(sys.modules[type(client).__module__])

        with pytest.raises(ValueError, match=r"^Cannot send header param `s`") as error:
            await client.header(
                revision=1, i=1, b=True, f=1.5, e=FooBarEnum.FOO, items=[1], s="ä"
            )
        assert type(error.value) is module["TestClientUnencodableParamError"]
        assert isinstance(error.value, module["TestClientError"])

    await async_client_tester(
        app,
        client_test,
        assert_format_of_generated_code=False,
    )


def test_unencodable_defaults(
    app_with_unencodable_defaults: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from typing import Any, cast

        import pytest

        from fastapi_typed_client import FastAPIClientUnencodableParamError

        # Omitting params whose server-side default is the passed value is lossless.
        result = client.defaults(
            q_required=1,
            q_none=None,
            q_empty=[],
            q_list_none=None,
            h_none=None,
            h_empty=[],
            c_none=None,
        )
        assert result.data == "(1, None, 5, [], None, None, 5, [], None, 5)"
        assert result.response.url.query == b"q_required=1"

        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=(
                r"^Cannot send query param `q_five`: `None` cannot be sent, and the "
                r"param is required or has a different default\.$"
            ),
        ):
            client.defaults(q_required=1, q_five=None)
        cases: list[tuple[dict[str, Any], str, str, Any]] = [
            ({"q_required": None}, "query", "q_required", None),
            ({"q_list_none": []}, "query", "q_list_none", []),
            ({"h_five": None}, "header", "h-five", None),
            ({"c_five": None}, "cookie", "c_five", None),
        ]
        for kwargs, location, name, value in cases:
            with pytest.raises(FastAPIClientUnencodableParamError) as error:
                cast(Any, client).defaults(**({"q_required": 1} | kwargs))
            assert error.value.location == location
            assert error.value.name == name
            assert error.value.value == value

        with pytest.raises(
            FastAPIClientUnencodableParamError, match=r"^Cannot send path param `p`"
        ):
            client.path(None)
        # Contributions of two dependencies to the same param have different defaults.
        with pytest.raises(
            FastAPIClientUnencodableParamError, match=r"^Cannot send query param `x`"
        ):
            client.ambiguous(None)
        result = client.ambiguous()
        assert result.data == "(None, 5)"

    client_tester(
        app_with_unencodable_defaults,
        client_test,
        import_client_base=True,
        assert_format_of_generated_code=False,
    )


async def test_unencodable_defaults_async(
    app_with_unencodable_defaults: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from typing import Any, cast

        import pytest

        from fastapi_typed_client import FastAPIClientUnencodableParamError

        # Omitting params whose server-side default is the passed value is lossless.
        result = await client.defaults(
            q_required=1,
            q_none=None,
            q_empty=[],
            q_list_none=None,
            h_none=None,
            h_empty=[],
            c_none=None,
        )
        assert result.data == "(1, None, 5, [], None, None, 5, [], None, 5)"
        assert result.response.url.query == b"q_required=1"

        with pytest.raises(
            FastAPIClientUnencodableParamError,
            match=(
                r"^Cannot send query param `q_five`: `None` cannot be sent, and the "
                r"param is required or has a different default\.$"
            ),
        ):
            await client.defaults(q_required=1, q_five=None)
        cases: list[tuple[dict[str, Any], str, str, Any]] = [
            ({"q_required": None}, "query", "q_required", None),
            ({"q_list_none": []}, "query", "q_list_none", []),
            ({"h_five": None}, "header", "h-five", None),
            ({"c_five": None}, "cookie", "c_five", None),
        ]
        for kwargs, location, name, value in cases:
            with pytest.raises(FastAPIClientUnencodableParamError) as error:
                await cast(Any, client).defaults(**({"q_required": 1} | kwargs))
            assert error.value.location == location
            assert error.value.name == name
            assert error.value.value == value

        with pytest.raises(
            FastAPIClientUnencodableParamError, match=r"^Cannot send path param `p`"
        ):
            await client.path(None)
        # Contributions of two dependencies to the same param have different defaults.
        with pytest.raises(
            FastAPIClientUnencodableParamError, match=r"^Cannot send query param `x`"
        ):
            await client.ambiguous(None)
        result = await client.ambiguous()
        assert result.data == "(None, 5)"

    await async_client_tester(
        app_with_unencodable_defaults,
        client_test,
        import_client_base=True,
        assert_format_of_generated_code=False,
    )


@pytest.mark.usefixtures("tmp_cwd")
def test_param_defaults_code(app_with_unencodable_defaults: FastAPI) -> None:
    generate_fastapi_typed_client(app_with_unencodable_defaults)
    code = Path("fastapi_client.py").read_text(encoding="utf-8")

    assert code.count("_param_defaults={") == 3
    assert (
        "            query_param_defaults={\n"
        '                "q_empty": [],\n'
        '                "q_list_none": None,\n'
        '                "q_none": None,\n'
        "            },\n"
    ) in code


@pytest.mark.usefixtures("tmp_cwd")
def test_opaque_defaults_are_not_evaluated() -> None:
    calls = list[str]()

    def factory() -> int:
        calls.append("factory")
        return 1

    app = FastAPI()

    @app.get("/opaque")
    def opaque(
        *,
        sentinel: Annotated[str, Query()] = cast("str", _Sentinel()),
        from_factory: Annotated[int, Header(default_factory=factory)],
    ) -> str:
        return repr((sentinel, from_factory))

    @app.get("/data-dependent")
    def data_dependent(model: Annotated[_DataDependentDefaultModel, Query()]) -> str:
        return repr(model)

    generate_fastapi_typed_client(app)
    code = Path("fastapi_client.py").read_text(encoding="utf-8")

    assert "_param_defaults={" not in code
    assert not calls
