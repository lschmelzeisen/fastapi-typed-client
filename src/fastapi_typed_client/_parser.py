from collections.abc import (
    AsyncIterable,
    AsyncIterator,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
)
from enum import Enum, auto
from http import HTTPMethod, HTTPStatus
from typing import Any, NamedTuple, get_args, get_origin

from fastapi._compat import ModelField
from fastapi.dependencies.utils import (
    _get_flat_fields_from_params,
    get_flat_dependant,
    get_typed_return_annotation,
)
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute, BaseRoute

from .client import FastAPIClientHTTPValidationError

_DISALLOWED_PARAM_NAMES = {
    "self",
    "client_exts",
    "raise_if_not_default_status",
    "HTTPMethod",
    "HTTPStatus",
}


class RouteParamKind(Enum):
    PATH = auto()
    QUERY = auto()
    HEADER = auto()
    COOKIE = auto()
    BODY = auto()


class RouteParam(NamedTuple):
    name: str
    alias: str | None
    kind: RouteParamKind
    type_: Any
    required: bool = False


class RouteResponse(NamedTuple):
    status: HTTPStatus
    type_: Any


class Route(NamedTuple):
    name: str
    path: str
    method: HTTPMethod
    default_status: HTTPStatus
    params: Sequence[RouteParam]
    responses: Mapping[HTTPStatus, RouteResponse]
    is_body_embedded: bool = False
    is_streaming_json: bool = False


def parse_routes(routes: Iterable[BaseRoute]) -> Sequence[Route]:
    result = [_parse_route(route) for route in routes if isinstance(route, APIRoute)]
    if not result:
        raise RuntimeError("Does not have any routes.")
    _check_duplicate_names(result)
    return result


def _parse_route(route: APIRoute) -> Route:
    if not route.name.isidentifier():
        raise RuntimeError(
            f"Route name `{route.name}` is not a valid Python identifier."
        )
    if not route.methods:
        raise RuntimeError(f"Routes {route.name} does not have any methods.")
    if len(route.methods) > 1:
        raise RuntimeError(
            f"Routes {route.name} with has more than one method: {', '.join(route.methods)}."
        )
    if not route.path_format:
        raise RuntimeError(
            f"Route {route.name} has unsupported path format `{route.path_format}`."
        )

    # TODO: would it be better to use route.response_class here?
    type_ = get_typed_return_annotation(route.endpoint)
    is_streaming_json = bool(
        isinstance(type_, type)
        and issubclass(type_, StreamingResponse)
        and issubclass(type_, JSONResponse)
    )

    params, is_body_embedded = _parse_params(route)
    responses, default_status = _parse_responses(
        route, has_params=bool(params), is_streaming_json=is_streaming_json
    )

    return Route(
        name=route.name,
        path=route.path_format,
        method=HTTPMethod(next(iter(route.methods))),
        default_status=default_status,
        params=params,
        is_body_embedded=is_body_embedded,
        responses={response.status: response for response in responses},
        is_streaming_json=is_streaming_json,
    )


def _parse_params(route: APIRoute) -> tuple[Sequence[RouteParam], bool]:
    result = list[RouteParam]()

    dependant = get_flat_dependant(route.dependant, skip_repeats=True)
    params_map: dict[RouteParamKind, list[ModelField]] = {
        # Couldn't find a better way to get flat fields.
        RouteParamKind.PATH: _get_flat_fields_from_params(dependant.path_params),
        RouteParamKind.QUERY: _get_flat_fields_from_params(dependant.query_params),
        RouteParamKind.HEADER: _get_flat_fields_from_params(dependant.header_params),
        RouteParamKind.COOKIE: _get_flat_fields_from_params(dependant.cookie_params),
        RouteParamKind.BODY: dependant.body_params,
    }

    seen_names = set[str]()
    disallowed_names = set[str]()
    duplicate_names = set[str]()

    for param_kind, params in params_map.items():
        for param in params:
            if param.name in _DISALLOWED_PARAM_NAMES:
                disallowed_names.add(param.name)
            if param.name in seen_names:
                duplicate_names.add(param.name)
            seen_names.add(param.name)

            result.append(
                RouteParam(
                    name=param.name,
                    alias=param.field_info.alias,
                    kind=param_kind,
                    type_=param.field_info.annotation or type(Any),
                    required=param.required,
                )
            )

    for names, error in (
        (disallowed_names, "not allowed"),
        (duplicate_names, "not unique"),
    ):
        if len(names) == 1:
            raise RuntimeError(
                f"Route {route.name} has parameter `{next(iter(names))}` whose name is "
                f"{error}."
            )
        if len(names) > 1:
            raise RuntimeError(
                f"Route {route.name} has parameter `{'`, `'.join(sorted(names))}` whose "
                f"names are {error}."
            )

    result.sort(key=lambda param: (not param.required, param.name))

    # Couldn't find a better way to find this out.
    is_body_embedded = route._embed_body_fields  # noqa: SLF001

    return result, is_body_embedded


def _parse_responses(
    route: APIRoute, *, has_params: bool, is_streaming_json: bool
) -> tuple[Sequence[RouteResponse], HTTPStatus]:
    result = list[RouteResponse]()

    default_status = (
        HTTPStatus(route.status_code) if route.status_code else HTTPStatus.OK
    )
    default_type = (
        route.response_field.field_info.annotation or type(Any)
        if route.response_field
        else type(Any)
    )
    default_type_origin = get_origin(default_type)
    if (
        is_streaming_json
        and isinstance(default_type_origin, type)
        and any(
            issubclass(default_type_origin, iter_class)
            for iter_class in (Iterator, Iterable, AsyncIterator, AsyncIterable)
        )
    ):
        default_type = get_args(default_type)[0]
    result.append(
        RouteResponse(
            status=default_status,
            type_=default_type,
        )
    )

    if has_params:
        result.append(
            RouteResponse(
                HTTPStatus.UNPROCESSABLE_CONTENT, FastAPIClientHTTPValidationError
            )
        )

    for status, response_field in route.response_fields.items():
        type_ = response_field.field_info.annotation or type(Any)
        result.append(RouteResponse(status=HTTPStatus(int(status)), type_=type_))

    result.sort(key=lambda response: response.status)

    return result, default_status


def _check_duplicate_names(routes: Iterable[Route]) -> None:
    seen_names = set()
    duplicate_names = set()
    for route in routes:
        if route.name not in seen_names:
            seen_names.add(route.name)
        else:
            duplicate_names.add(route.name)
    if duplicate_names:
        raise RuntimeError(
            f"Route names {','.join(sorted(duplicate_names))} occur multiple times."
        )
