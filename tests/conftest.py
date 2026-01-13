import subprocess
import sys
from collections.abc import Callable, Iterable, Iterator, Sequence
from importlib import import_module
from inspect import getsource
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Client
from pyrefly.__main__ import get_pyrefly_bin
from rich.console import Console
from ruff.__main__ import find_ruff_bin

import fastapi_typed_client
from fastapi_typed_client import generate_fastapi_typed_client

from . import shared
from .client_tester import (
    AsyncClientTester,
    AsyncClientTesterFunc,
    ClientTester,
    ClientTesterFunc,
)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def tmp_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def clear_test_imports() -> Iterator[None]:
    loaded_modules_before = set(sys.modules.keys())
    yield
    loaded_modules_after = set(sys.modules.keys())
    for module in sorted(loaded_modules_after - loaded_modules_before):
        del sys.modules[module]


@pytest.fixture
def tmp_import_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clear_test_imports: None,  # noqa: ARG001
) -> Path:
    monkeypatch.syspath_prepend(tmp_path)
    return tmp_path


@pytest.fixture(scope="session")
def pyrefly_bin() -> str:
    return get_pyrefly_bin()


@pytest.fixture(scope="session")
def ruff_bin() -> str:
    return find_ruff_bin()


@pytest.fixture
def client_tester(
    tmp_import_path: Path,
    pyrefly_bin: str,
    ruff_bin: str,
) -> ClientTester:
    def func(
        app: FastAPI,
        client_test_func: ClientTesterFunc,
        *,
        import_barrier: str | Iterable[str] | None = None,
        import_client_base: bool = False,
        raise_if_not_default_status: bool = False,
        httpx_client: Client | None = None,
        assert_type_check_passes: bool = True,
        assert_linting_passes: bool = True,
        assert_format_of_boilerplate_code: bool = True,
        assert_format_of_generated_code: bool = True,
    ) -> None:
        client_class, client_test = _client_tester_helper(
            app,
            client_test_func,
            import_barrier=import_barrier,
            import_client_base=import_client_base,
            raise_if_not_default_status=raise_if_not_default_status,
            assert_type_check_passes=assert_type_check_passes,
            assert_linting_passes=assert_linting_passes,
            assert_format_of_boilerplate_code=assert_format_of_boilerplate_code,
            assert_format_of_generated_code=assert_format_of_generated_code,
            async_=False,
            tmp_path=tmp_import_path,
            pyrefly_bin=pyrefly_bin,
            ruff_bin=ruff_bin,
        )
        if httpx_client:
            client = client_class(httpx_client)
            client_test(client)
        else:
            with client_class.from_app(app) as client:
                client_test(client)

    return func


@pytest.fixture
def async_client_tester(
    tmp_import_path: Path,
    pyrefly_bin: str,
    ruff_bin: str,
) -> AsyncClientTester:
    async def func(
        app: FastAPI,
        client_test_func: AsyncClientTesterFunc,
        *,
        import_barrier: str | Iterable[str] | None = None,
        import_client_base: bool = False,
        raise_if_not_default_status: bool = False,
        httpx_client: AsyncClient | None = None,
        assert_type_check_passes: bool = True,
        assert_linting_passes: bool = True,
        assert_format_of_boilerplate_code: bool = True,
        assert_format_of_generated_code: bool = True,
    ) -> None:
        client_class, client_test = _client_tester_helper(
            app,
            client_test_func,
            import_barrier=import_barrier,
            import_client_base=import_client_base,
            raise_if_not_default_status=raise_if_not_default_status,
            assert_type_check_passes=assert_type_check_passes,
            assert_linting_passes=assert_linting_passes,
            assert_format_of_boilerplate_code=assert_format_of_boilerplate_code,
            assert_format_of_generated_code=assert_format_of_generated_code,
            async_=True,
            tmp_path=tmp_import_path,
            pyrefly_bin=pyrefly_bin,
            ruff_bin=ruff_bin,
        )
        if httpx_client:
            client = client_class(httpx_client)
            await client_test(client)
        else:
            async with client_class.from_app(app) as client:
                await client_test(client)

    return func


def _client_tester_helper(
    app: FastAPI,
    client_test_func: ClientTesterFunc | AsyncClientTesterFunc,
    *,
    import_barrier: str | Iterable[str] | None,
    import_client_base: bool,
    raise_if_not_default_status: bool,
    assert_type_check_passes: bool,
    assert_linting_passes: bool,
    assert_format_of_boilerplate_code: bool,
    assert_format_of_generated_code: bool,
    async_: bool,
    tmp_path: Path,
    pyrefly_bin: str,
    ruff_bin: str,
) -> tuple[Any, Any]:
    shared_file = tmp_path / "shared.py"
    client_file = tmp_path / "client.py"
    client_test_file = tmp_path / "client_test.py"
    title = "TestClient"

    shared_file.write_text(getsource(shared), encoding="utf-8")

    generate_fastapi_typed_client(
        app,
        output_path=client_file,
        title=title,
        async_=async_,
        import_barrier=import_barrier,
        import_client_base=import_client_base,
        raise_if_not_default_status=raise_if_not_default_status,
        _add_test_markers=True,
    )

    client_file.write_text(
        client_file.read_text(encoding="utf-8").replace(
            "from tests.shared import", "from shared import"
        ),
        encoding="utf-8",
    )

    source_lines = getsource(client_test_func).splitlines()
    indent = next(i for i, c in enumerate(source_lines[0]) if not c.isspace())
    client_test_file.write_text(
        f"from client import {title}\n\n\n"
        f"{'' if not async_ else 'async '}def client_test(client: {title}) -> None:\n"
        + "".join(
            line[indent:]
            .removesuffix("  # type: ignore[client_tester_only]")
            .replace("from .shared import", "from shared import")
            .replace("from ..shared import", "from shared import")
            + "\n"
            for line in source_lines[1:]
        ),
        encoding="utf-8",
    )

    _assert_code_quality(
        pyrefly_bin=pyrefly_bin,
        ruff_bin=ruff_bin,
        client_file=client_file,
        client_test_file=client_test_file,
        assert_type_check_passes=assert_type_check_passes,
        assert_linting_passes=assert_linting_passes,
        assert_format_of_boilerplate_code=assert_format_of_boilerplate_code,
        assert_format_of_generated_code=assert_format_of_generated_code,
    )

    client_class = getattr(import_module(client_file.stem, "tests"), title)
    client_test = import_module(client_test_file.stem, "tests").client_test
    return client_class, client_test


def _get_callable_source(func: Callable[..., Any]) -> str:
    source_lines = getsource(func).splitlines()
    indent = next(i for i, c in enumerate(source_lines[0]) if not c.isspace())
    return "".join(f"{line[indent:]}\n" for line in source_lines)


def _assert_code_quality(
    *,
    pyrefly_bin: str,
    ruff_bin: str,
    client_file: Path,
    client_test_file: Path,
    assert_type_check_passes: bool,
    assert_linting_passes: bool,
    assert_format_of_boilerplate_code: bool,
    assert_format_of_generated_code: bool,
) -> None:
    if assert_type_check_passes:
        _assert_process_result(
            "Type-checking",
            (pyrefly_bin, "check"),
            client_file,
            client_test_file,
        )

    if assert_linting_passes:
        ruff_src_dirs = [
            str(Path(fastapi_typed_client.__file__).parent.parent),
            str(client_file.parent),
        ]
        _assert_process_result(
            "Linting",
            (
                ruff_bin,
                "check",
                *("--ignore", "S101"),
                *("--config", f"src = {ruff_src_dirs}"),
            ),
            client_file,
            client_test_file,
        )

    # Use `ruff format --check` to verify generated client files are formatted
    # correctly. Problem: Generated code combines two sources with different line
    # length requirements:
    # - `fastapi_typed_client.client` (follows project ruff settings)
    # - `fastapi_typed_client._generator` (assumes infinite line length)
    # Since ruff formatting settings aren't mid-file or per-file configurable, we
    # insert fmt on/off pragmas to test each section with its appropriate settings.
    client_code = client_file.read_text(encoding="utf-8")
    marker_before = "# TEST_MARKER_BEFORE_BOILERPLATE"
    marker_after = "# TEST_MARKER_AFTER_BOILERPLATE"
    fmt_on = "# fmt:on"
    fmt_off = "# fmt: off"

    if assert_format_of_boilerplate_code:
        client_file.write_text(
            f"{fmt_off}\n"
            + client_code.replace(marker_before, fmt_on).replace(marker_after, fmt_off),
            encoding="utf-8",
        )
        _assert_process_result(
            "Checking formatting of boilerplate code",
            (ruff_bin, "format", "--diff"),
            client_file,
        )

    if assert_format_of_generated_code:
        client_file.write_text(
            client_code.replace(marker_before, fmt_off).replace(marker_after, fmt_on),
            encoding="utf-8",
        )
        _assert_process_result(
            "Checking formatting of generated code",
            # Maximum line length that ruff supports.
            (ruff_bin, "format", "--diff", "--line-length", "320"),
            client_file,
        )


def _assert_process_result(desc: str, cmd: Sequence[str], *files: Path) -> None:
    result = subprocess.run(  # noqa: S603
        (*cmd, *map(str, files)),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        console = Console()
        console.print()
        console.rule(f"[red]{desc} failed[/red]", style="red", characters="=")
        for file in files:
            console.rule(str(file), style="plain", characters="-")
            console.print(file.read_text(encoding="utf-8"), end="")
        console.rule("Error", style="plain", characters="-")
        console.print(result.stdout, end="")
        console.rule(style="plain", characters="-")
        pytest.fail(f"{desc} failed.", pytrace=False)
