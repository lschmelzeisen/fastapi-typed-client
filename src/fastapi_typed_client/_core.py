from collections.abc import Iterable
from os import PathLike
from pathlib import Path

from fastapi import APIRouter, FastAPI

from ._generator import ClientCodeGenerator
from ._parser import parse_routes
from ._utils import load_import, to_snake_case, to_upper_camel_case
from .client import (
    FastAPIClientAsyncBase,
    FastAPIClientBase,
    FastAPIClientExtensions,
    FastAPIClientHTTPValidationError,
    FastAPIClientNotDefaultStatusError,
    FastAPIClientResult,
    FastAPIClientValidationError,
)

# Reserve these names to avoid confusion.
_RESERVED_TITLES = (
    FastAPIClientExtensions.__name__,
    FastAPIClientResult.__name__,
    FastAPIClientValidationError.__name__,
    FastAPIClientHTTPValidationError.__name__,
    FastAPIClientNotDefaultStatusError.__name__,
    FastAPIClientBase.__name__,
    FastAPIClientAsyncBase.__name__,
    "FASTAPI_CLIENT_NOT_REQUIRED",
)


def generate_fastapi_typed_client(
    app_or_import_str: FastAPI | APIRouter | str,
    *,
    output_path: PathLike[str] | str | None = None,
    title: str | None = None,
    async_: bool = False,
    import_barrier: str | Iterable[str] | None = None,
    import_client_base: bool = False,
    raise_if_not_default_status: bool = False,
    _add_test_markers: bool = False,
) -> None:
    app = (
        _import_app(app_or_import_str)
        if isinstance(app_or_import_str, str)
        else app_or_import_str
    )

    if not title:
        title = (
            to_upper_camel_case(app.title) + "Client"
            if isinstance(app, FastAPI)
            else "FastAPIClient"
        )
    if not title.isidentifier():
        raise RuntimeError(f"Title `{title}` is not a valid Python identifier.")
    if title in _RESERVED_TITLES:
        raise RuntimeError(f"Title `{title}` is reserved.")

    output_path = (
        Path(output_path)
        if output_path
        else Path(to_snake_case(title).replace("fast_api", "fastapi") + ".py")
    )

    if not import_barrier:
        import_barrier = []
    elif isinstance(import_barrier, str):
        import_barrier = [import_barrier]

    routes = parse_routes(app.routes)
    code = ClientCodeGenerator(
        title,
        async_,
        import_barrier,
        import_client_base,
        raise_if_not_default_status,
        _add_test_markers,
    ).generate(routes)

    output_path.write_text(code, encoding="utf-8")


def _import_app(app_import_str: str) -> FastAPI | APIRouter:
    module, _, name = app_import_str.partition(":")
    if not module or not name:
        raise RuntimeError(
            "App import string must be in the format `module.submodule:app_name`."
        )

    try:
        obj = load_import(module, name)
    except ModuleNotFoundError as e:
        if e.name != module:
            raise e from None
        raise RuntimeError(f"Could not import module `{module}`.") from e
    except AttributeError as e:
        raise RuntimeError(f"Attribute `{name}` not found in module `{module}`.") from e

    if not isinstance(obj, FastAPI) and not isinstance(obj, APIRouter):
        raise RuntimeError(
            f"App import string is not a FastAPI app, but a `{type(obj)}`."
        )

    return obj
