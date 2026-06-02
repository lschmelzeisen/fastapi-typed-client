from collections.abc import Sequence
from typing import Annotated, Any

import pytest
from fastapi import FastAPI, File, Form, UploadFile

from ..client_tester import AsyncClientTester, ClientTester
from ..shared import TextAndNum


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.post("/single", status_code=201)
    def single(file: UploadFile) -> dict[str, Any]:
        return {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": file.size,
        }

    @app.post("/multi", status_code=201)
    def multi(files: list[UploadFile]) -> list[str]:
        return [file.filename or "" for file in files]

    @app.post("/seq", status_code=201)
    def seq(files: Annotated[Sequence[UploadFile], File()]) -> int:
        return len(files)

    @app.post("/bytes-file", status_code=201)
    def bytes_file(data: Annotated[bytes, File()]) -> int:
        return len(data)

    @app.post("/form-scalars", status_code=201)
    def form_scalars(
        name: Annotated[str, Form()], age: Annotated[int, Form()]
    ) -> dict[str, Any]:
        return {"name": name, "age": age}

    @app.post("/model-form", status_code=201)
    def model_form(model: Annotated[TextAndNum, Form()]) -> str:
        return f"{model.text}-{model.num}"

    @app.post("/file-and-form", status_code=201)
    def file_and_form(file: UploadFile, note: Annotated[str, Form()]) -> dict[str, Any]:
        return {"filename": file.filename, "note": note}

    @app.post("/optional", status_code=201)
    def optional(
        file: UploadFile | None = None,
        note: Annotated[str | None, Form()] = None,
    ) -> dict[str, Any]:
        return {"has_file": file is not None, "note": note}

    @app.post("/optfile-reqform", status_code=201)
    def optfile_reqform(
        name: Annotated[str, Form()], file: UploadFile | None = None
    ) -> dict[str, Any]:
        return {"name": name, "has_file": file is not None}

    return app


def test_file_uploads(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from io import BytesIO

        from fastapi import UploadFile

        # The `FastAPIClientFile` alias accepts `UploadFile`, raw bytes, file-like
        # objects, and httpx `(filename, content, content_type)` tuples alike.
        result = client.single(UploadFile(filename="a.txt", file=BytesIO(b"hi")))
        assert result.response.request.headers["content-type"].startswith(
            "multipart/form-data"
        )
        assert b'filename="a.txt"' in result.response.request.content
        assert b"hi" in result.response.request.content
        assert result.data == {
            "filename": "a.txt",
            "content_type": "text/plain",
            "size": 2,
        }

        assert client.single(("b.txt", b"yo", "text/plain")).data == {
            "filename": "b.txt",
            "content_type": "text/plain",
            "size": 2,
        }
        raw = client.single(BytesIO(b"raw"), raise_if_not_default_status=True)
        assert raw.data["size"] == 3

        multi_result = client.multi([("x.txt", b"1"), ("y.txt", b"22")])
        assert multi_result.response.request.content.count(b'name="files"') == 2
        assert multi_result.data == ["x.txt", "y.txt"]

        assert client.seq([b"a", b"bb", b"ccc"]).data == 3
        assert client.bytes_file(b"12345").data == 5

    client_tester(app, client_test, assert_format_of_generated_code=False)


async def test_file_uploads_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from io import BytesIO

        from fastapi import UploadFile

        # The `FastAPIClientFile` alias accepts `UploadFile`, raw bytes, file-like
        # objects, and httpx `(filename, content, content_type)` tuples alike.
        result = await client.single(UploadFile(filename="a.txt", file=BytesIO(b"hi")))
        assert result.response.request.headers["content-type"].startswith(
            "multipart/form-data"
        )
        # Async multipart requests carry a streaming body, so `request.content` is not
        # readable here; the sync test covers the on-the-wire bytes.
        assert result.data == {
            "filename": "a.txt",
            "content_type": "text/plain",
            "size": 2,
        }

        assert (await client.single(("b.txt", b"yo", "text/plain"))).data == {
            "filename": "b.txt",
            "content_type": "text/plain",
            "size": 2,
        }
        raw = await client.single(BytesIO(b"raw"), raise_if_not_default_status=True)
        assert raw.data["size"] == 3

        multi_result = await client.multi([("x.txt", b"1"), ("y.txt", b"22")])
        assert multi_result.data == ["x.txt", "y.txt"]

        assert (await client.seq([b"a", b"bb", b"ccc"])).data == 3
        assert (await client.bytes_file(b"12345")).data == 5

    await async_client_tester(app, client_test, assert_format_of_generated_code=False)


def test_form_fields(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from httpx import QueryParams

        from ..shared import TextAndNum

        result = client.form_scalars(name="alice", age=30)
        assert (
            result.response.request.headers["content-type"]
            == "application/x-www-form-urlencoded"
        )
        assert dict(QueryParams(result.response.request.content)) == {
            "name": "alice",
            "age": "30",
        }
        assert result.data == {"name": "alice", "age": 30}

        # A model used as a `Form()` is flattened into top-level form fields.
        model_result = client.model_form(TextAndNum(text="foo", num=7))
        assert dict(QueryParams(model_result.response.request.content)) == {
            "text": "foo",
            "num": "7",
        }
        assert model_result.data == "foo-7"

    client_tester(app, client_test, assert_format_of_generated_code=False)


async def test_form_fields_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from httpx import QueryParams

        from ..shared import TextAndNum

        result = await client.form_scalars(name="alice", age=30)
        assert (
            result.response.request.headers["content-type"]
            == "application/x-www-form-urlencoded"
        )
        assert dict(QueryParams(result.response.request.content)) == {
            "name": "alice",
            "age": "30",
        }
        assert result.data == {"name": "alice", "age": 30}

        # A model used as a `Form()` is flattened into top-level form fields.
        model_result = await client.model_form(TextAndNum(text="foo", num=7))
        assert dict(QueryParams(model_result.response.request.content)) == {
            "text": "foo",
            "num": "7",
        }
        assert model_result.data == "foo-7"

    await async_client_tester(app, client_test, assert_format_of_generated_code=False)


def test_file_and_form(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from io import BytesIO

        from fastapi import UploadFile

        result = client.file_and_form(
            UploadFile(filename="a.txt", file=BytesIO(b"hi")), note="hello"
        )
        assert result.response.request.headers["content-type"].startswith(
            "multipart/form-data"
        )
        assert b'name="file"' in result.response.request.content
        assert b'name="note"' in result.response.request.content
        assert result.data == {"filename": "a.txt", "note": "hello"}

    client_tester(app, client_test, assert_format_of_generated_code=False)


async def test_file_and_form_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from io import BytesIO

        from fastapi import UploadFile

        result = await client.file_and_form(
            UploadFile(filename="a.txt", file=BytesIO(b"hi")), note="hello"
        )
        assert result.response.request.headers["content-type"].startswith(
            "multipart/form-data"
        )
        # Async multipart requests carry a streaming body, so `request.content` is not
        # readable here; the sync test covers the on-the-wire bytes.
        assert result.data == {"filename": "a.txt", "note": "hello"}

    await async_client_tester(app, client_test, assert_format_of_generated_code=False)


def test_optional_file_and_form(app: FastAPI, client_tester: ClientTester) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        from io import BytesIO

        from fastapi import UploadFile

        # All optional params omitted -> empty body, no content-type.
        omitted = client.optional()
        assert omitted.response.request.content == b""
        assert "content-type" not in omitted.response.request.headers
        assert omitted.data == {"has_file": False, "note": None}

        # Only the form field -> url-encoded (no file part).
        form_only = client.optional(note="hi")
        assert (
            form_only.response.request.headers["content-type"]
            == "application/x-www-form-urlencoded"
        )
        assert form_only.data == {"has_file": False, "note": "hi"}

        # File present -> multipart.
        with_file = client.optional(
            file=UploadFile(filename="a.txt", file=BytesIO(b"hi")), note="hi"
        )
        assert with_file.response.request.headers["content-type"].startswith(
            "multipart/form-data"
        )
        assert with_file.data == {"has_file": True, "note": "hi"}

        # Required form + omitted optional file -> url-encoded.
        reqform = client.optfile_reqform(name="bob")
        assert (
            reqform.response.request.headers["content-type"]
            == "application/x-www-form-urlencoded"
        )
        assert reqform.data == {"name": "bob", "has_file": False}

        reqform_file = client.optfile_reqform(
            name="bob", file=UploadFile(filename="a.txt", file=BytesIO(b"hi"))
        )
        assert reqform_file.response.request.headers["content-type"].startswith(
            "multipart/form-data"
        )
        assert reqform_file.data == {"name": "bob", "has_file": True}

    client_tester(app, client_test, assert_format_of_generated_code=False)


async def test_optional_file_and_form_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        from io import BytesIO

        from fastapi import UploadFile

        # All optional params omitted -> empty body, no content-type.
        omitted = await client.optional()
        assert omitted.response.request.content == b""
        assert "content-type" not in omitted.response.request.headers
        assert omitted.data == {"has_file": False, "note": None}

        # Only the form field -> url-encoded (no file part).
        form_only = await client.optional(note="hi")
        assert (
            form_only.response.request.headers["content-type"]
            == "application/x-www-form-urlencoded"
        )
        assert form_only.data == {"has_file": False, "note": "hi"}

        # File present -> multipart.
        with_file = await client.optional(
            file=UploadFile(filename="a.txt", file=BytesIO(b"hi")), note="hi"
        )
        assert with_file.response.request.headers["content-type"].startswith(
            "multipart/form-data"
        )
        assert with_file.data == {"has_file": True, "note": "hi"}

        # Required form + omitted optional file -> url-encoded.
        reqform = await client.optfile_reqform(name="bob")
        assert (
            reqform.response.request.headers["content-type"]
            == "application/x-www-form-urlencoded"
        )
        assert reqform.data == {"name": "bob", "has_file": False}

        reqform_file = await client.optfile_reqform(
            name="bob", file=UploadFile(filename="a.txt", file=BytesIO(b"hi"))
        )
        assert reqform_file.response.request.headers["content-type"].startswith(
            "multipart/form-data"
        )
        assert reqform_file.data == {"name": "bob", "has_file": True}

    await async_client_tester(app, client_test, assert_format_of_generated_code=False)


def test_file_uploads_import_client_base(
    app: FastAPI, client_tester: ClientTester
) -> None:
    def client_test(client: Any) -> None:  # noqa: ANN401
        result = client.single(b"hi", raise_if_not_default_status=True)
        assert result.response.request.headers["content-type"].startswith(
            "multipart/form-data"
        )
        assert result.data["size"] == 2

    client_tester(
        app,
        client_test,
        import_client_base=True,
        assert_format_of_generated_code=False,
    )


async def test_file_uploads_import_client_base_async(
    app: FastAPI, async_client_tester: AsyncClientTester
) -> None:
    async def client_test(client: Any) -> None:  # noqa: ANN401
        result = await client.single(b"hi", raise_if_not_default_status=True)
        assert result.response.request.headers["content-type"].startswith(
            "multipart/form-data"
        )
        assert result.data["size"] == 2

    await async_client_tester(
        app,
        client_test,
        import_client_base=True,
        assert_format_of_generated_code=False,
    )
