from base64 import b64encode
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Generator,
    Iterator,
    Mapping,
    MutableMapping,
    Sequence,
)
from contextlib import asynccontextmanager, contextmanager
from http import HTTPMethod, HTTPStatus
from typing import Any, Literal, NamedTuple, Self, TypedDict, override
from warnings import warn

from fastapi import FastAPI, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.sse import ServerSentEvent
from httpx2 import (
    USE_CLIENT_DEFAULT,
    ASGITransport,
    AsyncClient,
    Client,
    Response,
    Timeout,
)
from httpx2._types import FileTypes
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter, ValidationError

# List all imports of this file for usage by _generator.py here.
_IMPORTS = [
    Any,
    ConfigDict,
    HTTPMethod,
    HTTPStatus,
    Literal,
    Mapping,
    MutableMapping,
    NamedTuple,
    Response,
    Sequence,
    ServerSentEvent,
    Timeout,
    TypeAdapter,
    TypedDict,
    b64encode,
    jsonable_encoder,
    override,
    warn,
]
_IMPORTS_VALIDATION_ERROR = [BaseModel, Sequence]
_IMPORTS_SYNC_CLIENT = [Client, Generator, Iterator, contextmanager]
_IMPORTS_ASYNC_CLIENT = [
    AsyncClient,
    AsyncGenerator,
    AsyncIterator,
    asynccontextmanager,
    ASGITransport,
]
_IMPORTS_TYPE_CHECKING = [FastAPI]


type FastAPIClientFile = UploadFile | FileTypes


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


class FastAPIClientUnexpectedStatus(NamedTuple):
    status: HTTPStatus | None
    data: JsonValue
    response: Response


class FastAPIClientUnexpectedBody(NamedTuple):
    status: HTTPStatus
    data: JsonValue
    model: type[Any]
    validation_error: ValidationError
    response: Response


class FastAPIClientUnexpectedStreamItem(NamedTuple):
    data: JsonValue
    raw: str
    model: type[Any]
    validation_error: ValidationError


FastAPIClientUnexpectedResponse = (
    FastAPIClientUnexpectedStatus
    | FastAPIClientUnexpectedBody
    | FastAPIClientUnexpectedStreamItem
)


class FastAPIClientValidationError(BaseModel):
    loc: Sequence[str | int]
    msg: str
    type: str


class FastAPIClientHTTPValidationError(BaseModel):
    detail: Sequence[FastAPIClientValidationError]


class FastAPIClientError(Exception):
    pass


class FastAPIClientNotDefaultStatusError(FastAPIClientError):
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
        self._default_status = default_status
        self._result = result

    @property
    def default_status(self) -> HTTPStatus:
        return self._default_status

    @property
    def result(self) -> FastAPIClientResult[HTTPStatus, Any]:
        return self._result


class FastAPIClientUnexpectedResponseError(FastAPIClientError):
    def __init__(
        self,
        message: str,
        *,
        result: FastAPIClientUnexpectedResponse,
    ) -> None:
        super().__init__(message)
        self._result = result

    @property
    def result(self) -> FastAPIClientUnexpectedResponse:
        return self._result

    @staticmethod
    def _model_name(model: type[Any]) -> str:
        # Despite being typed as `type[Any]`, models aren't necessarily classes (e.g.
        # `list[int]` or `int | None`).
        return model.__name__ if isinstance(model, type) else str(model)


class FastAPIClientUnexpectedStatusError(FastAPIClientUnexpectedResponseError):
    def __init__(self, *, result: FastAPIClientUnexpectedStatus) -> None:
        status = (
            f"{result.status.value} {result.status.phrase}"
            if result.status is not None
            else f"{result.response.status_code} (non-standard)"
        )
        super().__init__(
            f"Received status {status}, which the route does not declare.",
            result=result,
        )
        self._status_result = result

    @property
    @override
    def result(self) -> FastAPIClientUnexpectedStatus:
        return self._status_result


class FastAPIClientUnexpectedBodyError(FastAPIClientUnexpectedResponseError):
    def __init__(self, *, result: FastAPIClientUnexpectedBody) -> None:
        super().__init__(
            f"Received status {result.status.value} {result.status.phrase} with a "
            "body that does not match the declared model "
            f"`{self._model_name(result.model)}`.",
            result=result,
        )
        self._body_result = result

    @property
    @override
    def result(self) -> FastAPIClientUnexpectedBody:
        return self._body_result


class FastAPIClientUnexpectedStreamItemError(FastAPIClientUnexpectedResponseError):
    def __init__(self, *, result: FastAPIClientUnexpectedStreamItem) -> None:
        super().__init__(
            "Received a stream item that does not match the declared model "
            f"`{self._model_name(result.model)}`.",
            result=result,
        )
        self._stream_item_result = result

    @property
    @override
    def result(self) -> FastAPIClientUnexpectedStreamItem:
        return self._stream_item_result


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


class FastAPIClientSSE[Data](ServerSentEvent):
    # Allows evaluating `FastAPIClientSSE[T | FastAPIClientUnexpectedStreamItem]` (which
    # holds a `ValidationError`) at runtime, e.g. in `assert_type()` or `cast()`.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    data: Data | None = None


FASTAPI_CLIENT_NOT_REQUIRED: Any = ...


class FastAPIClientBase:
    _json_value_adapter = TypeAdapter[JsonValue](JsonValue)

    def __init__(self, client: Client) -> None:
        self.client = client

    @classmethod
    @contextmanager
    def from_app(
        cls, app: FastAPI, base_url: str = "http://testserver"
    ) -> Generator[Self]:
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
    def _build_file_params(
        file_params: Mapping[str, Any] | None,
    ) -> list[tuple[str, Any]] | None:
        if file_params is None:
            return None
        result: list[tuple[str, Any]] = []
        for name, value in file_params.items():
            if value is FASTAPI_CLIENT_NOT_REQUIRED:
                continue
            values = value if isinstance(value, list) else [value]
            for v in values:
                if hasattr(v, "filename") and hasattr(v, "file"):
                    # `UploadFile`-like; duck-typed so we need not import it here.
                    result.append((name, (v.filename, v.file, v.content_type)))
                else:
                    # `bytes` / `str` / `IO[bytes]` / httpx2 `(name, content[, type])`.
                    result.append((name, v))
        return result or None

    @staticmethod
    def _build_form_params(
        form_params: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        if form_params is None:
            return None
        form: dict[str, Any] = {}
        for name, value in form_params.items():
            if value is FASTAPI_CLIENT_NOT_REQUIRED:
                continue
            encoded = jsonable_encoder(value)
            if isinstance(encoded, dict):
                # Model-as-`Form()`: flatten fields into top-level form fields
                # (only flat models round-trip; nested dicts don't url-encode).
                form.update(encoded)
            else:
                # Scalars get stringified by httpx2; lists become repeated fields.
                form[name] = encoded
        return form or None

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
        file_params: Mapping[str, Any] | None = None,
        form_params: Mapping[str, Any] | None = None,
        security_params: Sequence[FastAPIClientSecurityParam] | None = None,
        is_body_embedded: bool = False,
        streaming_kind: Literal[
            "json_lines", "server_sent_events", "raw_bytes", "raw_str"
        ]
        | None = None,
        raise_if_not_default_status: bool = False,
        raise_if_unexpected_response: bool = True,
        client_exts: FastAPIClientExtensions | None = None,
    ) -> (
        FastAPIClientResult[HTTPStatus, Any]
        | FastAPIClientUnexpectedStatus
        | FastAPIClientUnexpectedBody
    ):
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

        headers = self._filter_and_encode_params(header_params) or {}
        cookies = self._filter_and_encode_params(cookie_params) or {}
        queries = self._filter_and_encode_params(query_params) or {}
        self._apply_security_params(security_params, headers, cookies, queries)
        if cookies:
            # Mirror httpx2's per-request-cookies DeprecationWarning ourselves
            # (we bypass `Client.request()` via `build_request` + `send`).
            warn(
                "Setting per-request cookie parameters is deprecated because cookie"
                "persistence behaviour is ambiguous. Set cookies on the client"
                "instead.",
                DeprecationWarning,
                stacklevel=3,
            )

        timeout = client_exts.get("timeout", USE_CLIENT_DEFAULT)
        # Scuffed isinstance() check because we don't want to import
        # starlette.testclient.Testclient for users that don't need it.
        if (
            self.client.__class__.__name__ == "TestClient"
            and self.client.__class__.__module__ == "starlette.testclient"
            and timeout is not USE_CLIENT_DEFAULT
        ):
            warn(
                "Starlette's TestClient (which you probably use via "
                f"{self.__class__.__name__}.from_app()) does not support timeouts. See "
                "https://github.com/Kludex/starlette/issues/1108 for more information.",
                DeprecationWarning,
                stacklevel=3,
            )
            timeout = USE_CLIENT_DEFAULT  # Hide the warning generated by Starlette.

        files = self._build_file_params(file_params)
        form = self._build_form_params(form_params)
        if files is not None or form is not None:
            request = self.client.build_request(
                method.name,
                url,
                params=queries or None,
                headers=headers or None,
                cookies=cookies or None,
                data=form,
                files=files,
                timeout=timeout,
            )
        else:
            body = self._filter_and_encode_params(body_params)
            if body and not is_body_embedded:
                body = next(iter(body.values()))
            request = self.client.build_request(
                method.name,
                url,
                params=queries or None,
                headers=headers or None,
                cookies=cookies or None,
                json=body,
                timeout=timeout,
            )

        response = self.client.send(request, stream=streaming_kind is not None)
        return self._handle_response(
            response,
            default_status=default_status,
            models=models,
            streaming_kind=streaming_kind,
            raise_if_not_default_status=raise_if_not_default_status,
            raise_if_unexpected_response=raise_if_unexpected_response,
        )

    def _handle_response(
        self,
        response: Response,
        *,
        default_status: HTTPStatus,
        models: Mapping[HTTPStatus, Any],
        streaming_kind: Literal[
            "json_lines", "server_sent_events", "raw_bytes", "raw_str"
        ]
        | None,
        raise_if_not_default_status: bool,
        raise_if_unexpected_response: bool,
    ) -> (
        FastAPIClientResult[HTTPStatus, Any]
        | FastAPIClientUnexpectedStatus
        | FastAPIClientUnexpectedBody
    ):
        status = self._parse_status(response.status_code)
        if status is None or status not in models:
            text = self._read_text(response)
            unexpected_status = FastAPIClientUnexpectedStatus(
                status=status, data=self._parse_json_or_none(text), response=response
            )
            if raise_if_unexpected_response:
                raise FastAPIClientUnexpectedStatusError(result=unexpected_status)
            return unexpected_status

        model = models[status]
        if streaming_kind is not None and status == default_status:
            data = self._build_streaming_data(
                streaming_kind, response, model, raise_if_unexpected_response
            )
        else:
            # Streaming endpoints that return a non-default status (typically a JSON
            # error body) are read fully, just like non-streaming endpoints.
            text = self._read_text(response)
            try:
                # An empty body (e.g. 204 NO_CONTENT) is treated as JSON `null` so
                # the declared model still validates.
                data = TypeAdapter(model).validate_json(text or "null")
            except ValidationError as e:
                unexpected_body = FastAPIClientUnexpectedBody(
                    status=status,
                    data=self._parse_json_or_none(text),
                    model=model,
                    validation_error=e,
                    response=response,
                )
                if raise_if_unexpected_response:
                    raise FastAPIClientUnexpectedBodyError(
                        result=unexpected_body
                    ) from e
                return unexpected_body

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

    @staticmethod
    def _parse_status(status_code: int) -> HTTPStatus | None:
        try:
            return HTTPStatus(status_code)
        except ValueError:
            return None  # Non-standard status code (e.g. 499 or 520).

    @staticmethod
    def _read_text(response: Response) -> str:
        # Unlike iterating, reading retains the body (e.g. for `response.text`).
        try:
            response.read()
        finally:
            response.close()
        return response.text

    @classmethod
    def _parse_json_or_none(cls, text: str) -> JsonValue:
        try:
            return cls._json_value_adapter.validate_json(text)
        except ValidationError:
            return None

    @classmethod
    def _build_streaming_data(
        cls,
        streaming_kind: Literal[
            "json_lines", "server_sent_events", "raw_bytes", "raw_str"
        ],
        response: Response,
        model: Any,  # noqa: ANN401
        raise_if_unexpected_response: bool,
    ) -> Iterator[Any]:
        if streaming_kind == "raw_bytes":
            return cls._close_response_after(response, response.iter_bytes())
        if streaming_kind == "raw_str":
            return cls._close_response_after(response, response.iter_text())
        if streaming_kind == "json_lines":
            return cls._close_response_after(
                response,
                cls._iter_json_lines(response, model, raise_if_unexpected_response),
            )
        return cls._close_response_after(
            response, cls._iter_sse(response, model, raise_if_unexpected_response)
        )

    @staticmethod
    def _close_response_after(
        response: Response, source: Iterator[Any]
    ) -> Iterator[Any]:
        try:
            yield from source
        finally:
            response.close()

    @classmethod
    def _iter_json_lines(
        cls,
        response: Response,
        model: Any,  # noqa: ANN401
        raise_if_unexpected_response: bool,
    ) -> Iterator[Any]:
        adapter = TypeAdapter(model)
        for part in response.iter_lines():
            if part:
                yield cls._validate_stream_item(
                    adapter, part, model, raise_if_unexpected_response
                )

    @classmethod
    def _iter_sse(
        cls,
        response: Response,
        model: Any,  # noqa: ANN401
        raise_if_unexpected_response: bool,
    ) -> Iterator[Any]:
        adapter = TypeAdapter(model)
        for fields in cls._iter_sse_event_fields(response.iter_lines()):
            yield cls._build_sse(adapter, fields, model, raise_if_unexpected_response)

    @classmethod
    def _validate_stream_item(
        cls,
        adapter: TypeAdapter[Any],
        raw: str,
        model: Any,  # noqa: ANN401
        raise_if_unexpected_response: bool,
    ) -> Any:  # noqa: ANN401
        try:
            return adapter.validate_json(raw)
        except ValidationError as e:
            item = FastAPIClientUnexpectedStreamItem(
                data=cls._parse_json_or_none(raw),
                raw=raw,
                model=model,
                validation_error=e,
            )
            if raise_if_unexpected_response:
                raise FastAPIClientUnexpectedStreamItemError(result=item) from e
            return item

    @classmethod
    def _build_sse(
        cls,
        adapter: TypeAdapter[Any],
        fields: Mapping[str, Any],
        model: Any,  # noqa: ANN401
        raise_if_unexpected_response: bool,
    ) -> FastAPIClientSSE[Any]:
        event = FastAPIClientSSE[model].model_validate({**fields, "data": None})
        if "data" not in fields:
            return event
        # Attach the data without revalidating it (Pydantic couldn't validate an
        # unexpected stream item anyway).
        data = cls._validate_stream_item(
            adapter, fields["data"], model, raise_if_unexpected_response
        )
        return event.model_copy(update={"data": data})

    @classmethod
    def _iter_sse_event_fields(
        cls, lines: Iterator[str]
    ) -> Iterator[Mapping[str, Any]]:
        fields: dict[str, Any] = {}
        data_lines: list[str] = []
        comment_lines: list[str] = []
        for line in lines:
            if line:
                cls._accumulate_sse_line(line, fields, data_lines, comment_lines)
                continue
            event = cls._finalize_sse_event(fields, data_lines, comment_lines)
            if event is not None:
                yield event
            # Spec deviation: `lastEventId` doesn't persist across events. Each
            # yielded event reflects only what was on the wire for it; events
            # without an `id:` line surface as `id=None`.
            fields = {}
            data_lines = []
            comment_lines = []
        event = cls._finalize_sse_event(fields, data_lines, comment_lines)
        if event is not None:
            yield event

    @staticmethod
    def _accumulate_sse_line(
        line: str,
        fields: dict[str, Any],
        data_lines: list[str],
        comment_lines: list[str],
    ) -> None:
        if line.startswith(":"):
            comment_lines.append(line[1:].removeprefix(" "))
            return
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "data":
            data_lines.append(value)
        elif field in ("event", "id"):
            fields[field] = value
        elif field == "retry" and value.isascii() and value.isdigit():
            fields[field] = int(value)

    @staticmethod
    def _finalize_sse_event(
        fields: dict[str, Any], data_lines: list[str], comment_lines: list[str]
    ) -> dict[str, Any] | None:
        if data_lines:
            fields["data"] = "\n".join(data_lines)
        if comment_lines:
            fields["comment"] = "\n".join(comment_lines)
        # Spec deviation: comment- or metadata-only events (no `data:` lines)
        # are still dispatched. The spec says to drop them, but we surface them
        # so `FastAPIClientSSE.comment` is reachable from the client.
        return fields or None


class FastAPIClientAsyncBase:
    _json_value_adapter = TypeAdapter[JsonValue](JsonValue)

    def __init__(self, client: AsyncClient) -> None:
        self.client = client

    @classmethod
    @asynccontextmanager
    async def from_app(
        cls, app: FastAPI, base_url: str = "http://testserver"
    ) -> AsyncGenerator[Self]:
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
    def _build_file_params(
        file_params: Mapping[str, Any] | None,
    ) -> list[tuple[str, Any]] | None:
        if file_params is None:
            return None
        result: list[tuple[str, Any]] = []
        for name, value in file_params.items():
            if value is FASTAPI_CLIENT_NOT_REQUIRED:
                continue
            values = value if isinstance(value, list) else [value]
            for v in values:
                if hasattr(v, "filename") and hasattr(v, "file"):
                    # `UploadFile`-like; duck-typed so we need not import it here.
                    result.append((name, (v.filename, v.file, v.content_type)))
                else:
                    # `bytes` / `str` / `IO[bytes]` / httpx2 `(name, content[, type])`.
                    result.append((name, v))
        return result or None

    @staticmethod
    def _build_form_params(
        form_params: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        if form_params is None:
            return None
        form: dict[str, Any] = {}
        for name, value in form_params.items():
            if value is FASTAPI_CLIENT_NOT_REQUIRED:
                continue
            encoded = jsonable_encoder(value)
            if isinstance(encoded, dict):
                # Model-as-`Form()`: flatten fields into top-level form fields
                # (only flat models round-trip; nested dicts don't url-encode).
                form.update(encoded)
            else:
                # Scalars get stringified by httpx2; lists become repeated fields.
                form[name] = encoded
        return form or None

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
        file_params: Mapping[str, Any] | None = None,
        form_params: Mapping[str, Any] | None = None,
        security_params: Sequence[FastAPIClientSecurityParam] | None = None,
        is_body_embedded: bool = False,
        streaming_kind: Literal[
            "json_lines", "server_sent_events", "raw_bytes", "raw_str"
        ]
        | None = None,
        raise_if_not_default_status: bool = False,
        raise_if_unexpected_response: bool = True,
        client_exts: FastAPIClientExtensions | None = None,
    ) -> (
        FastAPIClientResult[HTTPStatus, Any]
        | FastAPIClientUnexpectedStatus
        | FastAPIClientUnexpectedBody
    ):
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

        headers = self._filter_and_encode_params(header_params) or {}
        cookies = self._filter_and_encode_params(cookie_params) or {}
        queries = self._filter_and_encode_params(query_params) or {}
        self._apply_security_params(security_params, headers, cookies, queries)
        if cookies:
            # Mirror httpx2's per-request-cookies DeprecationWarning ourselves
            # (we bypass `Client.request()` via `build_request` + `send`).
            warn(
                "Setting per-request cookie parameters is deprecated because cookie"
                "persistence behaviour is ambiguous. Set cookies on the client"
                "instead.",
                DeprecationWarning,
                stacklevel=3,
            )

        files = self._build_file_params(file_params)
        form = self._build_form_params(form_params)
        if files is not None or form is not None:
            request = self.client.build_request(
                method.name,
                url,
                params=queries or None,
                headers=headers or None,
                cookies=cookies or None,
                data=form,
                files=files,
                timeout=client_exts.get("timeout", USE_CLIENT_DEFAULT),
            )
        else:
            body = self._filter_and_encode_params(body_params)
            if body and not is_body_embedded:
                body = next(iter(body.values()))
            request = self.client.build_request(
                method.name,
                url,
                params=queries or None,
                headers=headers or None,
                cookies=cookies or None,
                json=body,
                timeout=client_exts.get("timeout", USE_CLIENT_DEFAULT),
            )

        response = await self.client.send(request, stream=streaming_kind is not None)
        return await self._handle_response(
            response,
            default_status=default_status,
            models=models,
            streaming_kind=streaming_kind,
            raise_if_not_default_status=raise_if_not_default_status,
            raise_if_unexpected_response=raise_if_unexpected_response,
        )

    async def _handle_response(
        self,
        response: Response,
        *,
        default_status: HTTPStatus,
        models: Mapping[HTTPStatus, Any],
        streaming_kind: Literal[
            "json_lines", "server_sent_events", "raw_bytes", "raw_str"
        ]
        | None,
        raise_if_not_default_status: bool,
        raise_if_unexpected_response: bool,
    ) -> (
        FastAPIClientResult[HTTPStatus, Any]
        | FastAPIClientUnexpectedStatus
        | FastAPIClientUnexpectedBody
    ):
        status = self._parse_status(response.status_code)
        if status is None or status not in models:
            text = await self._aread_text(response)
            unexpected_status = FastAPIClientUnexpectedStatus(
                status=status, data=self._parse_json_or_none(text), response=response
            )
            if raise_if_unexpected_response:
                raise FastAPIClientUnexpectedStatusError(result=unexpected_status)
            return unexpected_status

        model = models[status]
        if streaming_kind is not None and status == default_status:
            data = self._build_streaming_data(
                streaming_kind, response, model, raise_if_unexpected_response
            )
        else:
            # Streaming endpoints that return a non-default status (typically a JSON
            # error body) are read fully, just like non-streaming endpoints.
            text = await self._aread_text(response)
            try:
                # An empty body (e.g. 204 NO_CONTENT) is treated as JSON `null` so
                # the declared model still validates.
                data = TypeAdapter(model).validate_json(text or "null")
            except ValidationError as e:
                unexpected_body = FastAPIClientUnexpectedBody(
                    status=status,
                    data=self._parse_json_or_none(text),
                    model=model,
                    validation_error=e,
                    response=response,
                )
                if raise_if_unexpected_response:
                    raise FastAPIClientUnexpectedBodyError(
                        result=unexpected_body
                    ) from e
                return unexpected_body

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

    @staticmethod
    def _parse_status(status_code: int) -> HTTPStatus | None:
        try:
            return HTTPStatus(status_code)
        except ValueError:
            return None  # Non-standard status code (e.g. 499 or 520).

    @staticmethod
    async def _aread_text(response: Response) -> str:
        # Unlike iterating, reading retains the body (e.g. for `response.text`).
        try:
            await response.aread()
        finally:
            await response.aclose()
        return response.text

    @classmethod
    def _parse_json_or_none(cls, text: str) -> JsonValue:
        try:
            return cls._json_value_adapter.validate_json(text)
        except ValidationError:
            return None

    @classmethod
    def _build_streaming_data(
        cls,
        streaming_kind: Literal[
            "json_lines", "server_sent_events", "raw_bytes", "raw_str"
        ],
        response: Response,
        model: Any,  # noqa: ANN401
        raise_if_unexpected_response: bool,
    ) -> AsyncIterator[Any]:
        if streaming_kind == "raw_bytes":
            return cls._aclose_response_after(response, response.aiter_bytes())
        if streaming_kind == "raw_str":
            return cls._aclose_response_after(response, response.aiter_text())
        if streaming_kind == "json_lines":
            return cls._aclose_response_after(
                response,
                cls._aiter_json_lines(response, model, raise_if_unexpected_response),
            )
        return cls._aclose_response_after(
            response, cls._aiter_sse(response, model, raise_if_unexpected_response)
        )

    @staticmethod
    async def _aclose_response_after(
        response: Response, source: AsyncIterator[Any]
    ) -> AsyncIterator[Any]:
        try:
            async for item in source:
                yield item
        finally:
            await response.aclose()

    @classmethod
    async def _aiter_json_lines(
        cls,
        response: Response,
        model: Any,  # noqa: ANN401
        raise_if_unexpected_response: bool,
    ) -> AsyncIterator[Any]:
        adapter = TypeAdapter(model)
        async for part in response.aiter_lines():
            if part:
                yield cls._validate_stream_item(
                    adapter, part, model, raise_if_unexpected_response
                )

    @classmethod
    async def _aiter_sse(
        cls,
        response: Response,
        model: Any,  # noqa: ANN401
        raise_if_unexpected_response: bool,
    ) -> AsyncIterator[Any]:
        adapter = TypeAdapter(model)
        async for fields in cls._aiter_sse_event_fields(response.aiter_lines()):
            yield cls._build_sse(adapter, fields, model, raise_if_unexpected_response)

    @classmethod
    def _validate_stream_item(
        cls,
        adapter: TypeAdapter[Any],
        raw: str,
        model: Any,  # noqa: ANN401
        raise_if_unexpected_response: bool,
    ) -> Any:  # noqa: ANN401
        try:
            return adapter.validate_json(raw)
        except ValidationError as e:
            item = FastAPIClientUnexpectedStreamItem(
                data=cls._parse_json_or_none(raw),
                raw=raw,
                model=model,
                validation_error=e,
            )
            if raise_if_unexpected_response:
                raise FastAPIClientUnexpectedStreamItemError(result=item) from e
            return item

    @classmethod
    def _build_sse(
        cls,
        adapter: TypeAdapter[Any],
        fields: Mapping[str, Any],
        model: Any,  # noqa: ANN401
        raise_if_unexpected_response: bool,
    ) -> FastAPIClientSSE[Any]:
        event = FastAPIClientSSE[model].model_validate({**fields, "data": None})
        if "data" not in fields:
            return event
        # Attach the data without revalidating it (Pydantic couldn't validate an
        # unexpected stream item anyway).
        data = cls._validate_stream_item(
            adapter, fields["data"], model, raise_if_unexpected_response
        )
        return event.model_copy(update={"data": data})

    @classmethod
    async def _aiter_sse_event_fields(
        cls, lines: AsyncIterator[str]
    ) -> AsyncIterator[Mapping[str, Any]]:
        fields: dict[str, Any] = {}
        data_lines: list[str] = []
        comment_lines: list[str] = []
        async for line in lines:
            if line:
                cls._accumulate_sse_line(line, fields, data_lines, comment_lines)
                continue
            event = cls._finalize_sse_event(fields, data_lines, comment_lines)
            if event is not None:
                yield event
            # Spec deviation: `lastEventId` doesn't persist across events. Each
            # yielded event reflects only what was on the wire for it; events
            # without an `id:` line surface as `id=None`.
            fields = {}
            data_lines = []
            comment_lines = []
        event = cls._finalize_sse_event(fields, data_lines, comment_lines)
        if event is not None:
            yield event

    @staticmethod
    def _accumulate_sse_line(
        line: str,
        fields: dict[str, Any],
        data_lines: list[str],
        comment_lines: list[str],
    ) -> None:
        if line.startswith(":"):
            comment_lines.append(line[1:].removeprefix(" "))
            return
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "data":
            data_lines.append(value)
        elif field in ("event", "id"):
            fields[field] = value
        elif field == "retry" and value.isascii() and value.isdigit():
            fields[field] = int(value)

    @staticmethod
    def _finalize_sse_event(
        fields: dict[str, Any], data_lines: list[str], comment_lines: list[str]
    ) -> dict[str, Any] | None:
        if data_lines:
            fields["data"] = "\n".join(data_lines)
        if comment_lines:
            fields["comment"] = "\n".join(comment_lines)
        # Spec deviation: comment- or metadata-only events (no `data:` lines)
        # are still dispatched. The spec says to drop them, but we surface them
        # so `FastAPIClientSSE.comment` is reachable from the client.
        return fields or None
