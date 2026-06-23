from collections.abc import (
    AsyncIterable,
    Iterable,
    Mapping,
    Sequence,
)
from enum import Enum, auto
from http import HTTPMethod, HTTPStatus
from inspect import signature
from typing import Any, NamedTuple, cast, get_args, get_origin

from fastapi._compat import ModelField
from fastapi.datastructures import DefaultPlaceholder
from fastapi.dependencies.models import Dependant
from fastapi.dependencies.utils import (
    _get_flat_fields_from_params,
    get_flat_dependant,
    get_typed_return_annotation,
)
from fastapi.params import Body, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute, BaseRoute, _APIRouteLike, iter_route_contexts
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
from fastapi.sse import EventSourceResponse

from ._utils import to_snake_case
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
    FILE = auto()
    FORM = auto()
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


def parse_routes(routes: Sequence[BaseRoute]) -> Sequence[Route]:
    result = list[Route]()
    for route_context in iter_route_contexts(routes):
        if isinstance(route_context.original_route, APIRoute):
            result.append(_parse_route(cast(_APIRouteLike, route_context)))
    if not result:
        raise RuntimeError("Does not have any routes.")
    _check_duplicate_names(result)
    return result


def _parse_route(route: _APIRouteLike) -> Route:
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

    return_annotation = get_typed_return_annotation(route.endpoint)
    streaming_kind = _detect_streaming_kind(route, return_annotation)

    params, is_body_embedded = _parse_params(route)
    responses, default_status = _parse_responses(
        route,
        has_params=bool(params),
        streaming_kind=streaming_kind,
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
    route: _APIRouteLike,
    return_annotation: Any,  # noqa: ANN401
) -> RouteStreamingKind | None:
    # Mirror FastAPI's own flags, which stream JSON-Lines / SSE only for actual
    # generator endpoints.
    if route.is_sse_stream:
        return RouteStreamingKind.SERVER_SENT_EVENTS
    if route.is_json_stream:
        return RouteStreamingKind.JSON_LINES

    # Direct-return pattern: the endpoint constructs and returns a `Response` subclass
    # itself. These aren't generator functions, so FastAPI sets no flag for them and we
    # read the return annotation directly.
    if isinstance(return_annotation, type):
        if issubclass(return_annotation, EventSourceResponse):
            return RouteStreamingKind.SERVER_SENT_EVENTS
        if issubclass(return_annotation, StreamingResponse):
            # Pre-FastAPI-0.134 manual streaming pattern.
            if issubclass(return_annotation, JSONResponse):
                return RouteStreamingKind.JSON_LINES
            return RouteStreamingKind.RAW_BYTES

    # Explicit `response_class=StreamingResponse` on a generator endpoint streams raw
    # bytes/str. FastAPI sets neither flag and computes no item type for these, so the
    # yielded annotation is the only signal for telling `str` from `bytes`.
    if not isinstance(route.response_class, DefaultPlaceholder) and issubclass(
        route.response_class, StreamingResponse
    ):
        if _unwrap_iterable(return_annotation) is str:
            return RouteStreamingKind.RAW_STR
        return RouteStreamingKind.RAW_BYTES

    return None


def _unwrap_iterable(type_: Any) -> Any:  # noqa: ANN401
    # Item type of an iterable/container annotation, e.g. `Sequence[Item]` -> `Item`.
    # The `issubclass` match is intentionally broad (also covers `list` / `dict` /
    # `set`) so it unwraps container `response_model`s. FastAPI's `get_stream_item_type`
    # can't replace it: its origin allowlist excludes `Sequence` / `list`.
    origin = get_origin(type_)
    if isinstance(origin, type) and (
        issubclass(origin, Iterable) or issubclass(origin, AsyncIterable)
    ):
        args = get_args(type_)
        if args:
            return args[0]
    return None


def _parse_params(route: _APIRouteLike) -> tuple[Sequence[RouteParam], bool]:
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
    fields_params_map.update(_partition_body_fields(dependant.body_params))

    route_params_map: dict[RouteParamKind, Sequence[RouteParam]] = {
        kind: _fields_to_route_params(kind, fields, incompatible_names)
        for kind, fields in fields_params_map.items()
    }
    route_params_map[RouteParamKind.SECURITY] = _parse_security_params(route, dependant)

    if (
        route_params_map[RouteParamKind.FILE] or route_params_map[RouteParamKind.FORM]
    ) and route_params_map[RouteParamKind.BODY]:
        raise RuntimeError(
            f"Route {route.name} mixes file/form parameters with a JSON body "
            "parameter, which cannot be encoded in a single request."
        )

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


def _partition_body_fields(
    body_params: Sequence[ModelField],
) -> dict[RouteParamKind, list[ModelField]]:
    # Split body params by their `FieldInfo` subclass into file uploads, form fields,
    # and JSON body. Order matters: `File` is a `Form` is a `Body`.
    partitioned: dict[RouteParamKind, list[ModelField]] = {
        RouteParamKind.BODY: [],
        RouteParamKind.FILE: [],
        RouteParamKind.FORM: [],
    }
    for field in body_params:
        if isinstance(field.field_info, File):
            partitioned[RouteParamKind.FILE].append(field)
        elif isinstance(field.field_info, Form):
            partitioned[RouteParamKind.FORM].append(field)
        elif isinstance(field.field_info, Body):
            partitioned[RouteParamKind.BODY].append(field)
        else:
            raise RuntimeError(
                f"Body parameter `{field.name}` has unexpected field info type "
                f"`{type(field.field_info).__name__}`; expected a `fastapi.params.Body`."
            )
    return partitioned


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
    route: _APIRouteLike, dependant: Dependant
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
    route: _APIRouteLike, scheme: SecurityBase, param_name: str | None
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
    route: _APIRouteLike,
    *,
    has_params: bool,
    streaming_kind: RouteStreamingKind | None,
) -> tuple[Sequence[RouteResponse], HTTPStatus]:
    result = list[RouteResponse]()

    default_status = (
        HTTPStatus(route.status_code) if route.status_code else HTTPStatus.OK
    )
    default_type = _resolve_default_type(route, streaming_kind=streaming_kind)
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
    route: _APIRouteLike,
    *,
    streaming_kind: RouteStreamingKind | None,
) -> type:
    if streaming_kind is RouteStreamingKind.RAW_BYTES:
        return bytes
    if streaming_kind is RouteStreamingKind.RAW_STR:
        return str

    # FastAPI fills `stream_item_field` with the unwrapped item type (`ServerSentEvent`
    # wrapper dropped to `None`) only for generators, so gate on the flags: direct-return
    # JSONL/SSE streams carry their type in `response_field` and fall through below.
    if route.is_json_stream or route.is_sse_stream:
        stream_item_field = route.stream_item_field
        if stream_item_field and stream_item_field.field_info.annotation:
            return stream_item_field.field_info.annotation
        return type(Any)

    if route.response_field and route.response_field.field_info.annotation:
        type_ = route.response_field.field_info.annotation
        # Direct-return JSONL/SSE stream with a container `response_model` (e.g.
        # `Sequence[T]`): unwrap to the per-item type.
        if streaming_kind is not None:
            type_ = _unwrap_iterable(type_) or type_
        return type_

    # No `response_model`. A direct-return stream has no inner-type info → `Any`.
    if streaming_kind is not None:
        return type(Any)
    # Raw `inspect.signature` distinguishes `-> None` from an unannotated endpoint
    # (`Signature.empty`); `get_typed_return_annotation` collapses both to `None`.
    if signature(route.endpoint).return_annotation is None:
        return type(None)
    return type(Any)


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
