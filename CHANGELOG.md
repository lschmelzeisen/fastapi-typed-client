# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),  and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/lschmelzeisen/fastapi-typed-client/compare/v0.1.0...HEAD)

### Changed

- Update minimum supported Python version to 3.14. Older Python versions might work, but are not tested against.
- Update minimum required version of supported dependencies (`fastapi>=0.128.0`, `pydantic>=2.12.5`, `typer>=0.21.1`). Older dependency versions might work, but are not tested against.
- Use `HTTPStatus.UNPROCESSABLE_CONTENT` instead of `HTTPStatus.UNPROCESSABLE_ENTITY` (constant renamed with Python 3.13) in generated clients.

## [0.1.0](https://github.com/lschmelzeisen/fastapi-typed-client/releases/tag/v0.1.0) - 2025-10-18

Initial release.