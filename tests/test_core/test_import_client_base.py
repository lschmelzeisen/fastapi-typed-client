import re
from pathlib import Path

import pytest
from fastapi import FastAPI

from fastapi_typed_client import generate_fastapi_typed_client


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/foo")
    def foo() -> str:
        return "foo"

    return app


_RE_IMPORTS = re.compile(r"^import ([^\d\W][\w.]*)$", re.UNICODE | re.MULTILINE)
_RE_FROM_IMPORTS = re.compile(
    r"^from ([^\d\W][\w.]*) import", re.UNICODE | re.MULTILINE
)
_RE_CLASSES = re.compile(r"^class ([^\d\W]\w*)[:([]", re.UNICODE | re.MULTILINE)

pytestmark = pytest.mark.usefixtures("tmp_cwd")


def test_without_import_client_base(app: FastAPI) -> None:
    generate_fastapi_typed_client(app, import_client_base=False)
    generated_client = Path("fastapi_client.py").read_text(encoding="utf-8")

    assert not _RE_IMPORTS.findall(generated_client)
    for module in _RE_FROM_IMPORTS.findall(generated_client):
        assert not module.startswith(".")
        assert module != "fastapi_typed_client"
        assert not module.startswith("fastapi_typed_client")
    assert len(_RE_CLASSES.findall(generated_client)) > 1


def test_with_import_client_base(app: FastAPI) -> None:
    generate_fastapi_typed_client(app, import_client_base=True)
    generated_client = Path("fastapi_client.py").read_text(encoding="utf-8")

    assert not _RE_IMPORTS.findall(generated_client)
    from_imports = set(_RE_FROM_IMPORTS.findall(generated_client))
    assert "fastapi_typed_client.client" in from_imports
    for module in from_imports:
        assert not module.startswith(".")
        assert module != "fastapi_typed_client"
        if module != "fastapi_typed_client.client":
            assert not module.startswith("fastapi_typed_client")
    assert len(_RE_CLASSES.findall(generated_client)) == 1
