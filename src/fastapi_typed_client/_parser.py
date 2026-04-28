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
from inspect import signature
from typing import Any, NamedTuple, get_args, get_origin

from fastapi._compat import ModelField
from fastapi.datastructures import DefaultPlaceholder
from fastapi.dependencies.models import Dependant
from fastapi.dependencies.utils import (
    _get_flat_fields_from_params,
    get_flat_dependant,
    get_typed_return_annotation,
)
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.routing import APIRoute, BaseRoute
from fastapi.security import (
    APIKeyCookie,
    APIKeyHeader,
    APIKeyQuery,
    HTTPBasic,
    HTTPBearer,
    OAuth2AuthorizationCodeBearer,
    OAuth2PasswordBearer,
    OpenIdConnect,
)
from fastapi.security.base import SecurityBase
from fastapi.sse import EventSourceResponse, ServerSentEvent

from ._utils import to_snake_case
from .client import FastAPIClientHTTPValidationError

_DISALLOWED_PARAM_NAMES = {
    "self",
    "client_exts",
    "raise_if_not_default_status",
    "HTTPMethod",
    "HTTPStatus",
}

_ITERABLE_CLASSES = (Iterator, Iterable, AsyncIterator, AsyncIterable)


class RouteParamKind(Enum):
    PATH = auto()
    QUERY = auto()
    HEADER = auto()
    COOKIE = auto()
    BODY = auto()
    SECURITY = auto()


class RouteSecurityKind(Enum):
    HTTP_BEARER = auto()
    HTTP_BASIC = auto()
    API_KEY_HEADER = auto()
    API_KEY_COOKIE = auto()
    API_KEY_QUERY = auto()


class RouteStreamingKind(Enum):
    JSON_LINES = auto()
    SERVER_SENT_EVENTS = auto()
    RAW_BYTES = auto()
    RAW_STR = auto()


class RouteSecurity(NamedTuple):
    kind: RouteSecurityKind
    target_name: str


class RouteParam(NamedTuple):
    name: str
    alias: str | None
    kind: RouteParamKind
    type_: Any
    required: bool = False
    security: RouteSecurity | None = None


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
    streaming_kind: RouteStreamingKind | None = None


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
    return_annotation = get_typed_return_annotation(route.endpoint)
    streaming_kind = _detect_streaming_kind(route, return_annotation)

    params, is_body_embedded = _parse_params(route)
    responses, default_status = _parse_responses(
        route,
        has_params=bool(params),
        streaming_kind=streaming_kind,
        return_annotation=return_annotation,
    )

    return Route(
        name=route.name,
        path=route.path_format,
        method=HTTPMethod(next(iter(route.methods))),
        default_status=default_status,
        params=params,
        is_body_embedded=is_body_embedded,
        responses={response.status: response for response in responses},
        streaming_kind=streaming_kind,
    )


def _detect_streaming_kind(
    route: APIRoute,
    return_annotation: Any,  # noqa: ANN401
) -> RouteStreamingKind | None:
    response_class: type[Response] | None = (
        None
        if isinstance(route.response_class, DefaultPlaceholder)
        else route.response_class
    )

    # Direct-return pattern: the return annotation is a `Response` subclass that the
    # endpoint constructs and returns itself.
    if isinstance(return_annotation, type):
        if issubclass(return_annotation, EventSourceResponse):
            return RouteStreamingKind.SERVER_SENT_EVENTS
        if issubclass(return_annotation, StreamingResponse):
            # Pre-FastAPI-0.134 manual streaming pattern.
            if issubclass(return_annotation, JSONResponse):
                return RouteStreamingKind.JSON_LINES
            return RouteStreamingKind.RAW_BYTES

    inner = _unwrap_iterable(return_annotation)
    if response_class is not None:
        if issubclass(response_class, EventSourceResponse):
            return RouteStreamingKind.SERVER_SENT_EVENTS

        if issubclass(response_class, StreamingResponse):
            if inner is str:
                return RouteStreamingKind.RAW_STR
            return RouteStreamingKind.RAW_BYTES
    elif inner is not None and inner not in (bytes, str):
        return RouteStreamingKind.JSON_LINES

    return None


def _unwrap_iterable(type_: Any) -> Any:  # noqa: ANN401
    origin = get_origin(type_)
    if isinstance(origin, type) and any(
        issubclass(origin, c) for c in _ITERABLE_CLASSES
    ):
        args = get_args(type_)
        if args:
            return args[0]
    return None


def _parse_params(route: APIRoute) -> tuple[Sequence[RouteParam], bool]:
    incompatible_names = set[str]()
    seen_names = set[str]()
    disallowed_names = set[str]()
    duplicate_names = set[str]()

    dependant = get_flat_dependant(route.dependant, skip_repeats=True)

    fields_params_map: dict[RouteParamKind, list[ModelField]] = {
        RouteParamKind.PATH: dependant.path_params,
        RouteParamKind.QUERY: dependant.query_params,
        RouteParamKind.HEADER: dependant.header_params,
        RouteParamKind.COOKIE: dependant.cookie_params,
    }
    fields_params_map = {
        kind: _get_flat_fields_from_params(fields)
        for kind, fields in fields_params_map.items()
    }
    fields_params_map[RouteParamKind.BODY] = dependant.body_params

    route_params_map: dict[RouteParamKind, Sequence[RouteParam]] = {
        kind: _fields_to_route_params(kind, fields, incompatible_names)
        for kind, fields in fields_params_map.items()
    }
    route_params_map[RouteParamKind.SECURITY] = _parse_security_params(route, dependant)

    result = list[RouteParam]()
    for params in route_params_map.values():
        for param in params:
            if param.name in _DISALLOWED_PARAM_NAMES:
                disallowed_names.add(param.name)
            if param.name in seen_names:
                duplicate_names.add(param.name)
            seen_names.add(param.name)
            result.append(param)

    for names, error in (
        (disallowed_names, "not allowed"),
        (duplicate_names, "not unique"),
        (incompatible_names, "declared with incompatible definitions"),
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


def _fields_to_route_params(
    kind: RouteParamKind,
    fields: Sequence[ModelField],
    incompatible_names: set[str],
) -> Sequence[RouteParam]:
    result = list[RouteParam]()
    for group in _group_fields_by_alias(fields):
        primary = group[0]
        if not _is_field_group_compatible(group):
            incompatible_names.add(primary.name)
            continue
        result.append(
            RouteParam(
                name=primary.name,
                alias=primary.field_info.alias,
                kind=kind,
                type_=primary.field_info.annotation or type(Any),
                required=any(p.field_info.is_required() for p in group),
            )
        )
    return result


def _group_fields_by_alias(
    fields: Sequence[ModelField],
) -> Iterable[list[ModelField]]:
    # Two (sub-)dependencies of the same route may each declare the same parameter —
    # e.g. two `Depends` both taking `item_id: Annotated[int, Path()]`. These represent
    # one HTTP parameter, so we collapse them into a single group.
    grouped: dict[str, list[ModelField]] = {}
    for field in fields:
        grouped.setdefault(field.alias, []).append(field)
    return grouped.values()


def _is_field_group_compatible(group: Sequence[ModelField]) -> bool:
    # Contributions to the same parameter must be compatible: the client exposes
    # a single Python parameter with a single type, so Python name and annotation
    # must agree. Aliases already agree by construction of the group.
    primary = group[0]
    return not any(
        other.name != primary.name
        or other.field_info.annotation != primary.field_info.annotation
        for other in group[1:]
    )


def _parse_security_params(
    route: APIRoute, dependant: Dependant
) -> Sequence[RouteParam]:
    result = list[RouteParam]()
    seen_schemes = set[SecurityBase]()
    for dep in dependant.dependencies:
        if not dep._is_security_scheme:  # noqa: SLF001
            continue
        scheme = dep._security_scheme  # noqa: SLF001
        if scheme in seen_schemes:
            continue
        seen_schemes.add(scheme)
        result.append(_route_param_for_security_scheme(route, scheme, dep.name))
    return result


def _route_param_for_security_scheme(
    route: APIRoute, scheme: SecurityBase, param_name: str | None
) -> RouteParam:
    type_: type = str
    security_kind: RouteSecurityKind
    target_name: str

    if isinstance(
        scheme,
        HTTPBearer
        | OAuth2PasswordBearer
        | OAuth2AuthorizationCodeBearer
        | OpenIdConnect,
    ):
        security_kind = RouteSecurityKind.HTTP_BEARER
        target_name = "Authorization"
    elif isinstance(scheme, HTTPBasic):
        type_ = tuple[str, str]
        security_kind = RouteSecurityKind.HTTP_BASIC
        target_name = "Authorization"
    elif isinstance(scheme, APIKeyHeader):
        security_kind = RouteSecurityKind.API_KEY_HEADER
        target_name = scheme.model.name
    elif isinstance(scheme, APIKeyCookie):
        security_kind = RouteSecurityKind.API_KEY_COOKIE
        target_name = scheme.model.name
    elif isinstance(scheme, APIKeyQuery):
        security_kind = RouteSecurityKind.API_KEY_QUERY
        target_name = scheme.model.name
    else:
        raise RuntimeError(
            f"Route {route.name} uses unsupported security scheme "
            f"`{type(scheme).__name__}`."
        )

    return RouteParam(
        name=param_name or to_snake_case(scheme.scheme_name),
        alias=None,
        kind=RouteParamKind.SECURITY,
        type_=type_,
        required=getattr(scheme, "auto_error", True),
        security=RouteSecurity(kind=security_kind, target_name=target_name),
    )


def _parse_responses(
    route: APIRoute,
    *,
    has_params: bool,
    streaming_kind: RouteStreamingKind | None,
    return_annotation: Any,  # noqa: ANN401
) -> tuple[Sequence[RouteResponse], HTTPStatus]:
    result = list[RouteResponse]()

    default_status = (
        HTTPStatus(route.status_code) if route.status_code else HTTPStatus.OK
    )
    default_type = _resolve_default_type(
        route, streaming_kind=streaming_kind, return_annotation=return_annotation
    )
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


def _resolve_default_type(
    route: APIRoute,
    *,
    streaming_kind: RouteStreamingKind | None,
    return_annotation: Any,  # noqa: ANN401
) -> type:
    if streaming_kind is RouteStreamingKind.RAW_BYTES:
        return bytes
    if streaming_kind is RouteStreamingKind.RAW_STR:
        return str

    is_direct_return = isinstance(return_annotation, type) and issubclass(
        return_annotation, StreamingResponse
    )

    if route.response_field and route.response_field.field_info.annotation:
        type_ = route.response_field.field_info.annotation
    elif streaming_kind is not None and is_direct_return:
        # Direct-return pattern with no `response_model`: there's no inner-type
        # information available, so fall back to `Any`.
        return type(Any)
    elif streaming_kind is not None and return_annotation is not None:
        type_ = return_annotation
    elif signature(route.endpoint).return_annotation is None:
        # Use raw `inspect.signature` here (not the `return_annotation` param):
        # only the raw signature distinguishes `-> None` (literal `None`) from
        # an unannotated endpoint (`Signature.empty`). FastAPI's
        # `get_typed_return_annotation` collapses both to `None`.
        return type(None)
    else:
        return type(Any)

    if streaming_kind is not None:
        inner = _unwrap_iterable(type_)
        if inner is not None:
            type_ = inner

    if streaming_kind is RouteStreamingKind.SERVER_SENT_EVENTS and (
        type_ is ServerSentEvent
        or (isinstance(type_, type) and issubclass(type_, ServerSentEvent))
    ):
        return type(Any)

    return type_


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
