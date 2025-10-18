import sys
from pathlib import Path
from typing import Annotated

from rich import print  # noqa: A004
from typer import Argument, Exit, Option, Typer

app = Typer(name="fastapi-typed-client", rich_markup_mode="rich")


def _version_callback(value: bool) -> None:
    if value:
        from .__version__ import __version__

        print(f"{app.info.name} [green]{__version__}[/green]")
        raise Exit()


@app.callback()
def _callback(
    version: Annotated[
        bool,
        Option(
            "--version",
            help="Show the version and exit",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """
    Fully-typed client generator for your FastAPI app (mostly for testing)

    See: [link=https://github.com/lschmelzeisen/fastapi-typed-client]https://github.com/lschmelzeisen/fastapi-typed-client[/link]
    """


@app.command("generate")
def _generate(
    app_import_str: Annotated[
        str,
        Argument(
            help=(
                "The FastAPI app import string in the format "
                "`[bold]module.submodule:app_name[/bold]`."
            )
        ),
    ],
    *,
    output_path: Annotated[
        Path | None,
        Option(
            help=(
                "Path to write the generated client to. Defaults to --title (converted "
                "to snake_case) + `[bold].py[/bold]`."
            )
        ),
    ] = None,
    title: Annotated[
        str | None,
        Option(
            help=(
                "Title for the class of the generated client. Defaults to the FastAPI "
                "app title (converted to UpperCamelCase) + `[bold]Client[/bold]`."
            )
        ),
    ] = None,
    async_: Annotated[
        bool, Option("--async", help="Make generated client async.")
    ] = False,
    import_barrier: Annotated[
        list[str] | None,
        Option(
            metavar="MODULE",
            help=(
                "Module path(s) in format [bold]module.submodule[/bold] to set as "
                "import barriers. Forces types in submodules to be imported through "
                "the barrier rather than directly. Can be specified multiple times."
            ),
        ),
    ] = None,
    import_client_base: Annotated[
        bool,
        Option(
            "--import-client-base",
            help=(
                "Import the client base from [bold]fastapi_typed_client.client[/bold] "
                "instead of writing it to the output file. Intended when working with "
                "multiple generated clients at once."
            ),
        ),
    ] = False,
    raise_if_not_default_status: Annotated[
        bool,
        Option(
            "--raise-if-not-default-status",
            help=(
                "Client methods will raise an exception by default if the respective "
                "endpoint does not return its default status code. With or without "
                "option, this can also be controlled at each method call with the "
                "[bold]raise_if_not_default_status[/bold] parameter."
            ),
        ),
    ] = False,
) -> None:
    """
    Generate a new client for your FastAPI app.
    """

    sys.path.insert(0, str(Path.cwd()))
    try:
        from ._core import generate_fastapi_typed_client

        generate_fastapi_typed_client(
            app_import_str,
            output_path=output_path,
            title=title,
            async_=async_,
            import_barrier=import_barrier,
            import_client_base=import_client_base,
            raise_if_not_default_status=raise_if_not_default_status,
        )
    except BaseException as e:
        print(f"[red]Error[/red]: {e}", file=sys.stderr)
        raise Exit(code=1) from e
