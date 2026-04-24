from base64 import b64encode
from collections.abc import AsyncIterator, Iterator, Mapping, MutableMapping, Sequence
from contextlib import asynccontextmanager, contextmanager
from http import HTTPMethod, HTTPStatus
from typing import Any, Literal, NamedTuple, Self, TypedDict
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
    Literal,
    Mapping,
    MutableMapping,
    NamedTuple,
    Response,
    Sequence,
    Timeout,
    TypeAdapter,
    TypedDict,
    b64encode,
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


class FastAPIClientSecurityParam(NamedTuple):
    kind: Literal[
        "http_bearer",
        "http_basic",
        "api_key_header",
        "api_key_cookie",
        "api_key_query",
    ]
    name: str
    value: str | tuple[str, str] | None


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

    @staticmethod
    def _apply_security_params(
        security_params: Sequence[FastAPIClientSecurityParam] | None,
        header_params: MutableMapping[str, Any],
        cookie_params: MutableMapping[str, Any],
        query_params: MutableMapping[str, Any],
    ) -> None:
        for kind, name, value in security_params or ():
            if value is FASTAPI_CLIENT_NOT_REQUIRED or value is None:
                continue
            target: MutableMapping[str, Any]
            encoded: str
            if kind == "http_bearer" and isinstance(value, str):
                target, encoded = header_params, f"Bearer {value}"
            elif kind == "http_basic" and isinstance(value, tuple):
                user_pass = b64encode(f"{value[0]}:{value[1]}".encode()).decode("ascii")
                target, encoded = header_params, f"Basic {user_pass}"
            elif kind == "api_key_header" and isinstance(value, str):
                target, encoded = header_params, value
            elif kind == "api_key_cookie" and isinstance(value, str):
                target, encoded = cookie_params, value
            elif kind == "api_key_query" and isinstance(value, str):
                target, encoded = query_params, value
            else:
                raise TypeError(
                    f"Security param `{name}` of kind `{kind}` has "
                    f"incompatible value type `{type(value).__name__}`."
                )
            if name in target and target[name] is not FASTAPI_CLIENT_NOT_REQUIRED:
                raise RuntimeError(
                    f"Security param `{name}` conflicts with an already-set "
                    f"{kind.split('_', 1)[0]} param of the same name."
                )
            target[name] = encoded

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
        security_params: Sequence[FastAPIClientSecurityParam] | None = None,
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

        headers = self._filter_and_encode_params(header_params) or {}
        cookies = self._filter_and_encode_params(cookie_params) or {}
        queries = self._filter_and_encode_params(query_params) or {}
        self._apply_security_params(security_params, headers, cookies, queries)
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
            params=queries or None,
            headers=headers or None,
            cookies=cookies or None,
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
            # An empty body (e.g. 204 NO_CONTENT) is treated as JSON `null` so the
            # declared model still validatess.
            data = TypeAdapter(model).validate_json(response.text or "null")

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

    @staticmethod
    def _apply_security_params(
        security_params: Sequence[FastAPIClientSecurityParam] | None,
        header_params: MutableMapping[str, Any],
        cookie_params: MutableMapping[str, Any],
        query_params: MutableMapping[str, Any],
    ) -> None:
        for kind, name, value in security_params or ():
            if value is FASTAPI_CLIENT_NOT_REQUIRED or value is None:
                continue
            target: MutableMapping[str, Any]
            encoded: str
            if kind == "http_bearer" and isinstance(value, str):
                target, encoded = header_params, f"Bearer {value}"
            elif kind == "http_basic" and isinstance(value, tuple):
                user_pass = b64encode(f"{value[0]}:{value[1]}".encode()).decode("ascii")
                target, encoded = header_params, f"Basic {user_pass}"
            elif kind == "api_key_header" and isinstance(value, str):
                target, encoded = header_params, value
            elif kind == "api_key_cookie" and isinstance(value, str):
                target, encoded = cookie_params, value
            elif kind == "api_key_query" and isinstance(value, str):
                target, encoded = query_params, value
            else:
                raise TypeError(
                    f"Security param `{name}` of kind `{kind}` has "
                    f"incompatible value type `{type(value).__name__}`."
                )
            if name in target and target[name] is not FASTAPI_CLIENT_NOT_REQUIRED:
                raise RuntimeError(
                    f"Security param `{name}` conflicts with an already-set "
                    f"{kind.split('_', 1)[0]} param of the same name."
                )
            target[name] = encoded

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
        security_params: Sequence[FastAPIClientSecurityParam] | None = None,
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

        headers = self._filter_and_encode_params(header_params) or {}
        cookies = self._filter_and_encode_params(cookie_params) or {}
        queries = self._filter_and_encode_params(query_params) or {}
        self._apply_security_params(security_params, headers, cookies, queries)
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
            params=queries or None,
            headers=headers or None,
            cookies=cookies or None,
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
            # An empty body (e.g. 204 NO_CONTENT) is treated as JSON `null` so the
            # declared model still validate.
            data = TypeAdapter(model).validate_json(text or "null")

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
