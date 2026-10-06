# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),  and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.0](https://github.com/lschmelzeisen/fastapi-typed-client/releases/tag/v0.7.0) - 2026-10-06

### Added

- Handling of unexpected responses, i.e., a status code that the route does not declare (e.g. from a middleware, a reverse proxy, or a `500 Internal Server Error`; previously, this raised a bare `KeyError`, see [#1](https://github.com/lschmelzeisen/fastapi-typed-client/issues/1)) or a body that does not validate against the declared model:
  - By default, these raise `FastAPIClientUnexpectedStatusError` or `FastAPIClientUnexpectedBodyError`, and invalid items of JSON Lines and SSE streams raise `FastAPIClientUnexpectedStreamItemError` during iteration. All three subclass the new `FastAPIClientUnexpectedResponseError`, whose `result` holds the unexpected response.
  - With the new `raise_if_unexpected_response=False` parameter of generated client methods (or `--no-raise-if-unexpected-response` when generating), they are instead returned (or yielded) as the new `FastAPIClientUnexpectedStatus`, `FastAPIClientUnexpectedBody`, or `FastAPIClientUnexpectedStreamItem` (union alias `FastAPIClientUnexpectedResponse`), which are added to the return types.
  - Either way, they take precedence over `raise_if_not_default_status`.
- New exception base class `FastAPIClientError`.
- New `FastAPIClientUnencodableParamError` and `FastAPIClientConflictingParamError` (both subclassing `FastAPIClientError` and `ValueError`), raised before sending a request:
  - `FastAPIClientUnencodableParamError` if a path, query, header, cookie, or security parameter value can't be sent such that FastAPI parses it back into the same value. Previously, such values were silently altered or raised less specific errors, e.g. cookie values containing `;` (truncated), header or cookie values that aren't printable ASCII or have surrounding whitespace, path values with `.` or `..` segments, HTTP Basic credentials whose username contains `:` or that aren't ASCII, and security parameters of the wrong type (`TypeError`).
  - `FastAPIClientConflictingParamError` if a security parameter and another parameter would be sent as the same header, cookie, or query parameter (previously `RuntimeError`; now also detecting header names that differ only in case and conflicts between two security schemes).

### Changed

- Bodies that do not validate against the declared model (including stream items) now raise `FastAPIClientUnexpectedBodyError` (or `FastAPIClientUnexpectedStreamItemError`) instead of Pydantic's `ValidationError`, which is still available as `result.validation_error`.
- `FastAPIClientNotDefaultStatusError` now subclasses `FastAPIClientError`, and its attributes are now read-only.
- Generated client methods now always have overloads (also for routes with a single response).
- Booleans in path parameters are now sent as `true`/`false` (instead of `True`/`False`), like in other parameter locations.
- `None` or an empty list for a query, header, or cookie parameter is now omitted if FastAPI then falls back to the same value (e.g. `None` for `param: int | None = None`), and raises otherwise. Previously, `None` was sent as an empty query parameter, which FastAPI parses as `""` or rejects, and empty lists were always omitted, so FastAPI used the parameter's default even if it differs from `[]`.
- Update minimum required version of supported dependencies (`fastapi>=0.142.2`, `httpx2>=2.13.1`, `pydantic>=2.13.5`, `typer>=0.27.2`).

### Fixed

- Header and cookie parameters of non-string types (e.g. `int`, `bool`, or `list[int]`) are now sent instead of raising `TypeError` ([#2](https://github.com/lschmelzeisen/fastapi-typed-client/issues/2)), with list-typed headers sent as one header line per item.
- Path values are now percent-encoded (except for `/`), so values containing `?` or `#` are no longer truncated, and floats in paths no longer lose precision (e.g. `1e-25` was sent as `0`).
- `Decimal`, `timedelta`, and `SecretStr`/`SecretBytes` parameter values are now sent correctly (previously, `Decimal`s lost precision, `timedelta`s were sent as seconds, which FastAPI rejects, and secrets were sent masked).
- Parameters with a `validation_alias` are now sent under that name, and fields of Pydantic models used as `Header()` parameters with underscores converted to hyphens (unless they have an alias or the model uses `Header(convert_underscores=False)`).
- On streaming routes, responses with a non-default status code now retain their body (previously, `response.text` raised `ResponseNotRead`), and the streaming item type in the generated return type is now applied to the default response (previously, to the response with the lowest status code).

## [0.6.0](https://github.com/lschmelzeisen/fastapi-typed-client/releases/tag/v0.6.0) - 2026-08-27

### Changed

- Update minimum required version of supported dependencies (`fastapi>=0.141.1`, `httpx2>=2.12.0`, `typer>=0.27.1`).

## [0.5.0](https://github.com/lschmelzeisen/fastapi-typed-client/releases/tag/v0.5.0) - 2026-06-24

### Changed

- Update minimum required version of supported dependencies (`fastapi>=0.138.0`).

## [0.4.0](https://github.com/lschmelzeisen/fastapi-typed-client/releases/tag/v0.4.0) - 2026-06-17

### Added

- Support for [form](https://fastapi.tiangolo.com/tutorial/request-forms/) and [file-upload](https://fastapi.tiangolo.com/tutorial/request-files/) endpoints. Parameters declared with `UploadFile`, `File()`, or `Form()` are now sent with the correct encoding instead of being (incorrectly) JSON-encoded and rejected by the server:
  - The request is encoded as `multipart/form-data` when a file is present, otherwise as `application/x-www-form-urlencoded`.
  - File parameters are typed as the new `FastAPIClientFile` alias (`fastapi.UploadFile` unioned with httpx's `FileTypes`), so a caller may pass a `fastapi.UploadFile`, raw `bytes`, a file-like object, or an httpx `(filename, content, content_type)` tuple. Multiple-file parameters become `list[FastAPIClientFile]`.
  - A Pydantic model used as a `Form()` is flattened into its fields, and `fastapi.security.OAuth2PasswordRequestForm` (which expands into `Form()` fields) now works as a result.
  - Routes that mix a JSON body with form/file parameters are rejected during generation, since the two cannot be encoded in a single request.
- Support for [FastAPI security schemes](https://fastapi.tiangolo.com/tutorial/security/). Each scheme used by a route becomes a parameter on the generated client method, with the value placed into the correct HTTP header, cookie, or query on the wire. Supported schemes: `HTTPBearer`, `HTTPBasic`, `APIKeyHeader`, `APIKeyCookie`, `APIKeyQuery`, `OAuth2PasswordBearer`, `OAuth2AuthorizationCodeBearer`, and `OpenIdConnect`. For bearer-style schemes the parameter is a `str` token (the generated client prepends the `Bearer ` scheme); for `HTTPBasic` it is a `tuple[str, str]` of `(username, password)` (the client base64-encodes it); for API-key schemes it is a `str`. Schemes constructed with `auto_error=False` produce optional parameters. `HTTPDigest` remains unsupported.
- Support for FastAPI's native streaming endpoint patterns (added in FastAPI 0.134.0 / 0.135.0):
  - [Streaming JSON Lines](https://fastapi.tiangolo.com/tutorial/stream-json-lines/): endpoints declared as `-> Iterable[T]` / `-> AsyncIterable[T]` (without an explicit `response_class`) are detected automatically and the generated client method returns `Iterator[T]` (or `AsyncIterator[T]`) yielding parsed `T`s.
  - [Server-Sent Events](https://fastapi.tiangolo.com/tutorial/server-sent-events/): endpoints with `response_class=EventSourceResponse` are detected automatically. The generated client method returns `Iterator[FastAPIClientSSE[T]]` (or async equivalent), where the new `FastAPIClientSSE[Data]` class subclasses `fastapi.sse.ServerSentEvent` and exposes the `data` (parsed as `T`), `event`, `id`, `retry`, and `comment` fields.
  - [Raw bytes/string streaming](https://fastapi.tiangolo.com/advanced/stream-data/): endpoints with `response_class=StreamingResponse` returning `Iterable[bytes]` / `Iterable[str]` (or async equivalents) are detected automatically. The generated client method returns `Iterator[bytes]` / `Iterator[str]` (or async equivalents) yielding the chunks unmodified.

### Changed

- Endpoints annotated `-> None` now produce a generated client method whose `data` is typed as `None` (and whose `model` is `type[None]`) instead of `Any`.
- Unsupported Pydantic `FieldInfo` metadata in `Annotated` types now renders as the inner type (e.g. `Annotated[Cat | Dog, Field(discriminator="kind")]` becomes `Cat | Dog` instead of `Annotated[Cat | Dog, None]`). The accompanying warning now also names the dropped `FieldInfo` and inner type.
- Replace the `httpx` dependency with [`httpx2`](https://pypi.org/project/httpx2/), Pydantic's maintained continuation of `httpx`, in line with Starlette 1.2+ deprecating plain `httpx` in its test client. Generated clients now import from `httpx2` instead of `httpx`, so consumers of a generated client need `httpx2` installed.
- Update minimum required version of supported dependencies (`fastapi>=0.137.1`, `pydantic>=2.13.4`, `typer>=0.26.7`). Older dependency versions might work, but are not tested against.

### Fixed

- Handle empty response bodies (e.g. HTTP 204 `NO_CONTENT`). Previously, such endpoint (most commonly declared with `status_code=204`) raised `pydantic.ValidationError` in the generated client.
- Stop rejecting routes with shared sub-dependency params. Parameters declared by multiple (sub-)dependencies of the same route (e.g. two `Depends(...)` both taking `item_id: Annotated[UUID7, Path()]`) are now collapsed into a single client parameter instead of raising a false-positive `parameter ... whose name is not unique` error. Genuine conflicts — same name with different kinds (e.g. Query vs Header), same kind with different aliases, or same kind+name with incompatible types — still fail generation, now with a clearer message distinguishing "not unique" from "declared with incompatible definitions".

## [0.3.0](https://github.com/lschmelzeisen/fastapi-typed-client/releases/tag/v0.3.0) - 2026-04-15

### Changed

- Update minimum required version of supported dependencies (`fastapi>=0.135.3`, `pydantic>=2.13.0`, `rich>=15.0.0`, `typer>=0.24.1`). Older dependency versions might work, but are not tested against.

## [0.2.0](https://github.com/lschmelzeisen/fastapi-typed-client/releases/tag/v0.2.0) - 2026-01-13

### Changed

- Update minimum supported Python version to 3.14. Older Python versions might work, but are not tested against.
- Update minimum required version of supported dependencies (`fastapi>=0.128.0`, `pydantic>=2.12.5`, `typer>=0.21.1`). Older dependency versions might work, but are not tested against.
- Stop quoting type annotations in generated clients (possible thanks to Python 3.14's [deferred evaluation of annotations](https://docs.python.org/3/whatsnew/3.14.html#pep-649-pep-749-deferred-evaluation-of-annotations)).
- Use `HTTPStatus.UNPROCESSABLE_CONTENT` instead of `HTTPStatus.UNPROCESSABLE_ENTITY` (constant renamed with Python 3.13) in generated clients.

## [0.1.0](https://github.com/lschmelzeisen/fastapi-typed-client/releases/tag/v0.1.0) - 2025-10-18

Initial release.