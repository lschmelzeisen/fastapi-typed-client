from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Protocol

from fastapi import FastAPI
from httpx import AsyncClient, Client

type ClientTesterFunc = Callable[[Any], None]
type AsyncClientTesterFunc = Callable[[Any], Awaitable[None]]


class ClientTester(Protocol):
    def __call__(
        self,
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
    ) -> None: ...


class AsyncClientTester(Protocol):
    async def __call__(
        self,
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
    ) -> None: ...
