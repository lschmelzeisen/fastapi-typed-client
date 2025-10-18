import re
from pathlib import Path
from typing import assert_type

import pytest
from fastapi import APIRouter, FastAPI

from fastapi_typed_client import generate_fastapi_typed_client


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.get("/foo")
    def foo() -> str:
        return "foo"

    @app.post("/bar")
    def bar() -> str:
        return "bar"

    return app


@pytest.fixture
def app_source() -> str:
    return (
        "from fastapi import FastAPI\n\n"
        "app = FastAPI()\n\n\n"
        '@app.get("/foo")\n'
        "def foo() -> str:\n"
        '    return "foo"\n\n\n'
        '@app.post("/bar")\n'
        "def bar() -> str:\n"
        '    return "bar"\n'
    )


_RE_METHODS = re.compile(r"^ {4}def ([^\d\W]\w*)[([]", re.UNICODE | re.MULTILINE)


def assert_correct_generated_client() -> None:
    # Use as heuristic that we have a class with the correct name and one the method
    # definition for each app route.
    generated_client = Path("fastapi_client.py").read_text(encoding="utf-8")
    assert "class FastAPIClient" in generated_client
    methods = _RE_METHODS.findall(generated_client)
    assert methods.count("foo") == 1
    assert methods.count("bar") == 1


pytestmark = pytest.mark.usefixtures("tmp_cwd")


def test_with_fastapi_app(app: FastAPI) -> None:
    generate_fastapi_typed_client(app)
    assert_correct_generated_client()


def test_with_fastapi_router(app: FastAPI) -> None:
    router = app.router
    assert_type(app.router, APIRouter)
    generate_fastapi_typed_client(router)
    assert_correct_generated_client()


@pytest.mark.parametrize("module_name", ["foo", "foo.bar"])
@pytest.mark.parametrize("app_name", ["app", "api"])
@pytest.mark.usefixtures("tmp_import_path")
def test_with_import_str(app_source: str, module_name: str, app_name: str) -> None:
    if "." in module_name:
        super_module, _, sub_module = module_name.partition(".")
        super_module_path = Path(super_module)
        super_module_path.mkdir()
        (super_module_path / "init.py").write_text("", encoding="utf-8")
        module_path = super_module_path / f"{sub_module}.py"
    else:
        module_path = Path(f"{module_name}.py")

    module_path.write_text(app_source.replace("app", app_name), encoding="utf-8")
    generate_fastapi_typed_client(f"{module_name}:{app_name}")
    assert_correct_generated_client()
