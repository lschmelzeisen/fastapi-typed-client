from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager, contextmanager
from http import HTTPMethod, HTTPStatus
from typing import Any, NamedTuple, Self, TypedDict
from warnings import warn

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from httpx import (
    USE_CLIENT_DEFAULT,
    ASGITransport,
    AsyncClient,
    Client,
    Response,
    Timeout,
)
from pydantic import BaseModel, TypeAdapter

# List all imports of this file for usage by _generator.py here.
_IMPORTS = [
    Any,
    HTTPMethod,
    HTTPStatus,
    Mapping,
    NamedTuple,
    Response,
    Self,
    Timeout,
    TypeAdapter,
    TypedDict,
    jsonable_encoder,
    warn,
]
_IMPORTS_VALIDATION_ERROR = [BaseModel, Sequence]
_IMPORTS_SYNC_CLIENT = [Client, Iterator, contextmanager]
_IMPORTS_ASYNC_CLIENT = [AsyncClient, AsyncIterator, asynccontextmanager, ASGITransport]
_IMPORTS_TYPE_CHECKING = [FastAPI]


class FastAPIClientExtensions(TypedDict, total=False):
    timeout: (
        float
        | tuple[float | None, float | None, float | None, float | None]
        | Timeout
        | None
    )


class FastAPIClientResult[Status: HTTPStatus, Model](NamedTuple):
    status: Status
    data: Model
    model: type[Model]
    response: Response


class FastAPIClientValidationError(BaseModel):
    loc: Sequence[str | int]
    msg: str
    type: str


class FastAPIClientHTTPValidationError(BaseModel):
    detail: Sequence[FastAPIClientValidationError]


class FastAPIClientNotDefaultStatusError(Exception):
    def __init__(
        self,
        *,
        default_status: HTTPStatus,
        result: FastAPIClientResult[HTTPStatus, Any],
    ) -> None:
        super().__init__(
            f"Expected default status {default_status.value} {default_status.phrase}, "
            f"but received {result.status.value} {result.status.phrase}."
        )
        self.default_status = default_status
        self.result = result


FASTAPI_CLIENT_NOT_REQUIRED: Any = ...


class FastAPIClientBase:
    def __init__(self, client: Client) -> None:
        self.client = client

    @classmethod
    @contextmanager
    def from_app(
        cls, app: FastAPI, base_url: str = "http://testserver"
    ) -> Iterator[Self]:
        from fastapi.testclient import TestClient

        with TestClient(app, base_url=base_url) as client:
            yield cls(client)

    @staticmethod
    def _filter_and_encode_params(
        params: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        if params is None:
            return None
        return {
            param: jsonable_encoder(value)
            for param, value in params.items()
            if value is not FASTAPI_CLIENT_NOT_REQUIRED
        } or None

    def _route_handler(
        self,
        *,
        path: str,
        method: HTTPMethod,
        default_status: HTTPStatus,
        models: Mapping[HTTPStatus, Any],
        path_params: Mapping[str, Any] | None = None,
        query_params: Mapping[str, Any] | None = None,
        header_params: Mapping[str, Any] | None = None,
        cookie_params: Mapping[str, Any] | None = None,
        body_params: Mapping[str, Any] | None = None,
        is_body_embedded: bool = False,
        is_streaming_json: bool = False,
        raise_if_not_default_status: bool = False,
        client_exts: FastAPIClientExtensions | None = None,
    ) -> FastAPIClientResult[HTTPStatus, Any]:
        if not client_exts:
            client_exts = {}

        url = path
        for param, value in (self._filter_and_encode_params(path_params) or {}).items():
            value_str = (
                f"{value:0.20f}".rstrip("0").rstrip(".")
                if isinstance(value, float)
                else str(value)
            )
            url = url.replace(f"{{{param}}}", value_str)

        body = self._filter_and_encode_params(body_params)
        if body and not is_body_embedded:
            body = next(iter(body.values()))

        cookies = self._filter_and_encode_params(cookie_params)
        if cookies:
            warn(
                "Setting cookie parameters directly on an endpoint function is "
                "experimental. (This is the cause for the DeprecationWarning by httpx "
                "below.)",
                UserWarning,
                stacklevel=3,
            )

        timeout = client_exts.get("timeout")
        # Scuffed isinstance() check because we don't want to import
        # starlette.testclient.Testclient for users that don't need it.
        if (
            self.client.__class__.__name__ == "TestClient"
            and self.client.__class__.__module__ == "starlette.testclient"
            and timeout
        ):
            warn(
                "Starlette's TestClient (which you probably use via "
                f"{self.__class__.__name__}.from_app()) does not support timeouts. See "
                "https://github.com/Kludex/starlette/issues/1108 for more information.",
                DeprecationWarning,
                stacklevel=3,
            )
            timeout = USE_CLIENT_DEFAULT  # Hide the warning generated by Starlette.

        response = self.client.request(
            method.name,
            url,
            params=self._filter_and_encode_params(query_params),
            headers=self._filter_and_encode_params(header_params),
            cookies=cookies,
            json=body,
            timeout=timeout or USE_CLIENT_DEFAULT,
        )
        status = HTTPStatus(response.status_code)

        model = models[status]
        if is_streaming_json and status == default_status:

            def data_iter() -> Iterator[Any]:
                for part in response.iter_lines():
                    yield TypeAdapter(model).validate_json(part)

            data = data_iter()
        else:
            data = TypeAdapter(model).validate_json(response.text)

        result = FastAPIClientResult(
            status=status,
            data=data,
            model=model,
            response=response,
        )
        if status != default_status and raise_if_not_default_status:
            raise FastAPIClientNotDefaultStatusError(
                default_status=default_status, result=result
            )
        return result


class FastAPIClientAsyncBase:
    def __init__(self, client: AsyncClient) -> None:
        self.client = client

    @classmethod
    @asynccontextmanager
    async def from_app(
        cls, app: FastAPI, base_url: str = "http://testserver"
    ) -> AsyncIterator[Self]:
        async with AsyncClient(
            transport=ASGITransport(app), base_url=base_url
        ) as client:
            yield cls(client)

    @staticmethod
    def _filter_and_encode_params(
        params: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        if params is None:
            return None
        return {
            param: jsonable_encoder(value)
            for param, value in params.items()
            if value is not FASTAPI_CLIENT_NOT_REQUIRED
        } or None

    async def _route_handler(
        self,
        *,
        path: str,
        method: HTTPMethod,
        default_status: HTTPStatus,
        models: Mapping[HTTPStatus, Any],
        path_params: Mapping[str, Any] | None = None,
        query_params: Mapping[str, Any] | None = None,
        header_params: Mapping[str, Any] | None = None,
        cookie_params: Mapping[str, Any] | None = None,
        body_params: Mapping[str, Any] | None = None,
        is_body_embedded: bool = False,
        is_streaming_json: bool = False,
        raise_if_not_default_status: bool = False,
        client_exts: FastAPIClientExtensions | None = None,
    ) -> FastAPIClientResult[HTTPStatus, Any]:
        if not client_exts:
            client_exts = {}

        url = path
        for param, value in (self._filter_and_encode_params(path_params) or {}).items():
            value_str = (
                f"{value:0.20f}".rstrip("0").rstrip(".")
                if isinstance(value, float)
                else str(value)
            )
            url = url.replace(f"{{{param}}}", value_str)

        body = self._filter_and_encode_params(body_params)
        if body and not is_body_embedded:
            body = next(iter(body.values()))

        cookies = self._filter_and_encode_params(cookie_params)
        if cookies:
            warn(
                "Setting cookie parameters directly on an endpoint function is "
                "experimental. (This is the cause for the DeprecationWarning by httpx "
                "below.)",
                UserWarning,
                stacklevel=3,
            )

        response = await self.client.request(
            method.name,
            url,
            params=self._filter_and_encode_params(query_params),
            headers=self._filter_and_encode_params(header_params),
            cookies=cookies,
            json=body,
            timeout=client_exts.get("timeout") or USE_CLIENT_DEFAULT,
        )
        status = HTTPStatus(response.status_code)

        model = models[status]
        if is_streaming_json and status == default_status:

            async def data_iter() -> AsyncIterator[Any]:
                async for part in response.aiter_lines():
                    yield TypeAdapter(model).validate_json(part)

            data = data_iter()
        else:
            text = ""
            async for part in response.aiter_text():
                text += part
            data = TypeAdapter(model).validate_json(text)

        result = FastAPIClientResult(
            status=status,
            data=data,
            model=model,
            response=response,
        )
        if status != default_status and raise_if_not_default_status:
            raise FastAPIClientNotDefaultStatusError(
                default_status=default_status, result=result
            )
        return result
