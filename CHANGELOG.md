# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),  and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/lschmelzeisen/fastapi-typed-client/compare/v0.3.0...HEAD)

### Added

- Support for [FastAPI security schemes](https://fastapi.tiangolo.com/tutorial/security/). Each scheme used by a route becomes a parameter on the generated client method, with the value placed into the correct HTTP header, cookie, or query on the wire. Supported schemes: `HTTPBearer`, `HTTPBasic`, `APIKeyHeader`, `APIKeyCookie`, `APIKeyQuery`, `OAuth2PasswordBearer`, `OAuth2AuthorizationCodeBearer`, and `OpenIdConnect`. For bearer-style schemes the parameter is a `str` token (the generated client prepends the `Bearer ` scheme); for `HTTPBasic` it is a `tuple[str, str]` of `(username, password)` (the client base64-encodes it); for API-key schemes it is a `str`. Schemes constructed with `auto_error=False` produce optional parameters. `HTTPDigest` and `OAuth2PasswordRequestForm` remain unsupported.
- Support for FastAPI's native streaming endpoint patterns (added in FastAPI 0.134.0 / 0.135.0):
  - [Streaming JSON Lines](https://fastapi.tiangolo.com/tutorial/stream-json-lines/): endpoints declared as `-> Iterable[T]` / `-> AsyncIterable[T]` (without an explicit `response_class`) are detected automatically and the generated client method returns `Iterator[T]` (or `AsyncIterator[T]`) yielding parsed `T`s.
  - [Server-Sent Events](https://fastapi.tiangolo.com/tutorial/server-sent-events/): endpoints with `response_class=EventSourceResponse` are detected automatically. The generated client method returns `Iterator[FastAPIClientSSE[T]]` (or async equivalent), where the new `FastAPIClientSSE[Data]` class subclasses `fastapi.sse.ServerSentEvent` and exposes the `data` (parsed as `T`), `event`, `id`, `retry`, and `comment` fields.
  - [Raw bytes/string streaming](https://fastapi.tiangolo.com/advanced/stream-data/): endpoints with `response_class=StreamingResponse` returning `Iterable[bytes]` / `Iterable[str]` (or async equivalents) are detected automatically. The generated client method returns `Iterator[bytes]` / `Iterator[str]` (or async equivalents) yielding the chunks unmodified.

### Changed

- Endpoints annotated `-> None` now produce a generated client method whose `data` is typed as `None` (and whose `model` is `type[None]`) instead of `Any`.

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