from pathlib import Path

import pytest
from pytest_mock import MockerFixture, MockType
from typer.testing import CliRunner

from fastapi_typed_client.cli import app


@pytest.fixture
def mock_generate_fastapi_typed_client(mocker: MockerFixture) -> MockType:
    return mocker.patch("fastapi_typed_client._core.generate_fastapi_typed_client")


cli_runner = CliRunner()


def test_option_defaults(mock_generate_fastapi_typed_client: MockType) -> None:
    cli_runner.invoke(app, ("generate", "foo:bar"))
    mock_generate_fastapi_typed_client.assert_called_once_with(
        "foo:bar",
        output_path=None,
        title=None,
        async_=False,
        import_barrier=None,
        import_client_base=False,
        raise_if_not_default_status=False,
    )


def test_option_values(mock_generate_fastapi_typed_client: MockType) -> None:
    cli_runner.invoke(
        app,
        (
            "generate",
            "foo:bar",
            *("--output-path", "foo.py"),
            *("--title", "BarClient"),
            "--async",
            *("--import-barrier", "baz"),
            *("--import-barrier", "quux"),
            "--import-client-base",
            "--raise-if-not-default-status",
        ),
    )
    mock_generate_fastapi_typed_client.assert_called_once_with(
        "foo:bar",
        output_path=Path("foo.py"),
        title="BarClient",
        async_=True,
        import_barrier=["baz", "quux"],
        import_client_base=True,
        raise_if_not_default_status=True,
    )


def test_error(mock_generate_fastapi_typed_client: MockType) -> None:
    mock_generate_fastapi_typed_client.side_effect = RuntimeError
    result = cli_runner.invoke(app, ("generate", "foo:bar"))
    assert result.exit_code != 0
