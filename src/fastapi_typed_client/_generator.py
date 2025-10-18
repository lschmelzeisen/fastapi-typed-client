from collections import defaultdict
from collections.abc import AsyncIterator, Collection, Iterable, Iterator, Sequence
from collections.abc import Set as AbstractSet
from enum import Enum, auto
from functools import cache
from http import HTTPMethod, HTTPStatus
from importlib.util import find_spec
from inspect import getsource
from sys import stdlib_module_names
from typing import Any, Literal, NamedTuple, overload
from warnings import warn

from ._parser import Route, RouteParam, RouteParamKind, RouteResponse
from ._utils import Import, ImportRegistry, dq_str_repr, indent, to_constant_case
from .client import (
    _IMPORTS,
    _IMPORTS_ASYNC_CLIENT,
    _IMPORTS_SYNC_CLIENT,
    _IMPORTS_TYPE_CHECKING,
    _IMPORTS_VALIDATION_ERROR,
    FastAPIClientAsyncBase,
    FastAPIClientBase,
    FastAPIClientExtensions,
    FastAPIClientHTTPValidationError,
    FastAPIClientNotDefaultStatusError,
    FastAPIClientResult,
    FastAPIClientValidationError,
)


class _Identifiers(NamedTuple):
    client_extensions: str
    result: str
    validation_error: str
    http_validation_error: str
    not_default_status_error: str
    not_required: str
    base_class: str
    client_class: str

    def replace_in_code(self, code: str) -> str:
        replacements = {
            FastAPIClientExtensions.__name__: self.client_extensions,
            FastAPIClientResult.__name__: self.result,
            FastAPIClientValidationError.__name__: self.validation_error,
            FastAPIClientHTTPValidationError.__name__: self.http_validation_error,
            FastAPIClientNotDefaultStatusError.__name__: self.not_default_status_error,
            "FASTAPI_CLIENT_NOT_REQUIRED": self.not_required,
            FastAPIClientBase.__name__: self.base_class,
            FastAPIClientAsyncBase.__name__: self.base_class,
        }
        for old, new in replacements.items():
            code = code.replace(old, new)
        return code


class _ImportGroup(Enum):
    STDLIB = auto()
    SITE_PACKAGE = auto()
    LOCAL = auto()


class ClientCodeGenerator:
    def __init__(
        self,
        title: str,
        async_: bool,
        import_barriers: Iterable[str],
        import_client_base: bool,
        raise_if_not_default_status: bool,
        add_test_markers: bool,
    ) -> None:
        self._title = title
        self._async = async_
        self._base_class = FastAPIClientBase if not async_ else FastAPIClientAsyncBase
        self._import_client_base = import_client_base
        self._raise_if_not_default_status = raise_if_not_default_status
        self._add_test_markers = add_test_markers
        self._impr = ImportRegistry()
        for import_barrier in import_barriers:
            self._impr.add_barrier(import_barrier)
        self._idents = self._init_identifiers()

    def _init_identifiers(self) -> _Identifiers:
        if self._import_client_base:
            return _Identifiers(
                client_extensions=FastAPIClientExtensions.__name__,
                result=FastAPIClientResult.__name__,
                validation_error=FastAPIClientValidationError.__name__,
                http_validation_error=FastAPIClientHTTPValidationError.__name__,
                not_default_status_error=FastAPIClientNotDefaultStatusError.__name__,
                not_required="FASTAPI_CLIENT_NOT_REQUIRED",
                base_class=self._base_class.__name__,
                client_class=self._title,
            )
        return _Identifiers(
            client_extensions=f"{self._title}Extensions",
            result=f"{self._title}Result",
            validation_error=f"{self._title}ValidationError",
            http_validation_error=f"{self._title}HTTPValidationError",
            not_default_status_error=f"{self._title}NotDefaultStatusError",
            not_required=(
                to_constant_case(self._title).replace("FAST_API", "FASTAPI")
                + "_NOT_REQUIRED"
            ),
            base_class=self._title,
            client_class=self._title,
        )

    def generate(self, routes: Sequence[Route]) -> str:
        for route in routes:
            for param in route.params:
                self._impr.add_reserved_ident(param.name)

        codes = ["", "", self._get_boilerplate_code(routes)]
        codes.extend(indent(self._get_route_code(route)) for route in routes)
        # This relies on the side effects to self._impr of the previous code generating
        # functions, so we can only call it at the end.
        codes[0] = _ImportCodeGenerator(self._impr).generate()

        return "\n".join(codes)

    def _get_boilerplate_code(self, routes: Sequence[Route]) -> str:
        return _BoilerplateCodeGenerator(
            self._impr, self._base_class, self._idents, self._add_test_markers
        ).generate(routes, self._import_client_base)

    def _get_route_code(self, route: Route) -> str:
        return self._get_route_signature_code(route) + indent(
            f"return {'await ' if self._async else ''}self._route_handler(  # type: ignore\n"
            f"    path={dq_str_repr(route.path)},\n"
            f"    method={self._impr(HTTPMethod)}.{route.method.name},\n"
            f"    default_status={self._impr(HTTPStatus)}.{route.default_status.name},\n"
            + indent(self._get_models_dict_code(route.responses.values()))
            + indent(self._get_params_dicts_code(route.params))
            + indent(self._get_optional_params_code(route))
            + "    raise_if_not_default_status=raise_if_not_default_status,\n"
            "    client_exts=client_exts,\n"
            ")\n"
        )

    def _get_route_signature_code(self, route: Route) -> str:
        if len(route.responses) == 1:
            return f"{self._get_route_overload_signature_code(route, route.responses.values(), None)}:\n"

        return (
            f"@{self._impr(overload)}\n"
            f"{self._get_route_overload_signature_code(route, route.responses[route.default_status], True)}: ...\n"
            f"@{self._impr(overload)}\n"
            f"{self._get_route_overload_signature_code(route, route.responses.values(), False)}: ...\n"
            f"{self._get_route_overload_signature_code(route, None, None)}:\n"
        )

    def _get_route_overload_signature_code(
        self,
        route: Route,
        responses: RouteResponse | Collection[RouteResponse] | None,
        raise_if_not_default_status: bool | None,
    ) -> str:
        return (
            f"{'async ' if self._async else ''}def {route.name}(\n"
            + "    self,\n"
            + indent(self._get_route_specific_params_code(route.params))
            + indent(self._get_route_generic_params_code(raise_if_not_default_status))
            + ") -> "
            + self._get_route_responses_code(responses, route.is_streaming_json)
        )

    def _get_route_specific_params_code(self, params: Sequence[RouteParam]) -> str:
        code = ""
        for param in params:
            code += f"{param.name}: {self._impr(param.type_)}"
            if not param.required:
                code += f" = {self._idents.not_required}"
            code += ",\n"
        return code

    def _get_route_generic_params_code(
        self, raise_if_not_default_status: bool | None
    ) -> str:
        raise_if_not_default_status_str = {
            True: self._impr(Literal[True]),
            False: self._impr(Literal[False]),
            None: "bool",
        }[raise_if_not_default_status]
        code = "*,\n"
        code += f"raise_if_not_default_status: {raise_if_not_default_status_str}"
        if (
            raise_if_not_default_status is None
            or raise_if_not_default_status == self._raise_if_not_default_status
        ):
            code += f" = {self._raise_if_not_default_status!r}"
        code += ",\n"
        code += f"client_exts: {self._idents.client_extensions} | None = None,\n"
        return code

    def _get_route_responses_code(
        self,
        responses: RouteResponse | Collection[RouteResponse] | None,
        is_streaming_json: bool,
    ) -> str:
        if not responses:
            return f"{self._idents.result}[{self._impr(HTTPStatus)}, {self._impr(Any)}]"

        if isinstance(responses, RouteResponse):
            responses = (responses,)

        code = ""
        if len(responses) > 1:
            code += "(\n    "
        for i, response in enumerate(responses):
            if i != 0:
                code += "\n    | "
            response_type = response.type_
            if i == 0 and is_streaming_json:
                response_type = (Iterator if not self._async else AsyncIterator)[
                    response_type
                ]
            code += (
                f"{self._idents.result}["
                f"{self._impr(Literal)}[{self._impr(HTTPStatus)}.{response.status.name}], "
                f"{self._get_response_type_code(response_type)}"
                "]"
            )
        if len(responses) > 1:
            code += "\n)"
        return code

    def _get_response_type_code(self, type_: Any) -> str:  # noqa: ANN401
        if type_ is FastAPIClientHTTPValidationError:
            return self._idents.http_validation_error
        return self._impr(type_)

    def _get_models_dict_code(self, responses: Collection[RouteResponse]) -> str:
        lines = []
        for response in responses:
            status_str = f"{self._impr(HTTPStatus)}.{response.status.name}"
            type_str = self._get_response_type_code(response.type_)
            lines.append(f"{status_str}: {type_str},\n")
        return f"models={{\n{indent(''.join(lines))}}},"

    @staticmethod
    def _get_params_dicts_code(params: Sequence[RouteParam]) -> str:
        code = ""
        for param_kind in RouteParamKind:
            kind_params = [param for param in params if param.kind is param_kind]
            if not kind_params:
                continue
            code += f"{param_kind.name.lower()}_params={{\n"
            for param in kind_params:
                code += f"    {dq_str_repr(param.alias or param.name)}: {param.name},\n"
            code += "},\n"
        return code

    @staticmethod
    def _get_optional_params_code(route: Route) -> str:
        code = ""
        if route.is_body_embedded:
            code += f"is_body_embedded={route.is_body_embedded},\n"
        if route.is_streaming_json:
            code += f"is_streaming_json={route.is_streaming_json},\n"
        return code


class _BoilerplateCodeGenerator:
    def __init__(
        self,
        impr: ImportRegistry,
        base_class: type[FastAPIClientBase | FastAPIClientAsyncBase],
        idents: _Identifiers,
        add_test_markers: bool,
    ) -> None:
        self._impr = impr
        self._base_class = base_class
        self._idents = idents
        self._add_test_markers = add_test_markers

    def generate(self, routes: Sequence[Route], import_client_base: bool) -> str:
        has_not_required_params = any(
            not param.required for route in routes for param in route.params
        )
        has_validation_errors = any(
            response.type_ is FastAPIClientHTTPValidationError
            for route in routes
            for response in route.responses.values()
        )
        if import_client_base:
            return self._generate_with_import_client_base(
                has_not_required_params, has_validation_errors
            )
        return self._generate_without_import_client_base(has_validation_errors)

    def _generate_with_import_client_base(
        self,
        has_not_required_params: bool,
        has_validation_errors: bool,
    ) -> str:
        # Manually write imports here so that modules are imported from specific
        # submodule instead of top-level module.
        for import_name in [
            self._base_class.__name__,
            self._idents.client_extensions,
            self._idents.result,
            self._idents.http_validation_error if has_validation_errors else None,
            self._idents.not_required if has_not_required_params else None,
        ]:
            if import_name:
                self._impr.add_import(
                    Import(module=self._base_class.__module__, name=import_name)
                )
        return f"class {self._idents.client_class}({self._impr(self._base_class)}):"

    def _generate_without_import_client_base(self, has_validation_errors: bool) -> str:
        # Adding Self to one of the *_IMPORTS constant makes type checking fail.
        self._impr.add_import(Import(module="typing", name="Self"))

        # Can't programmatically look up import location of constants, so have to
        # hard-code those here.
        self._impr.add_import(Import(module="httpx", name="USE_CLIENT_DEFAULT"))

        # Manually specify where warn is imported from, because otherwise it resolves to
        # `from _warnings import warn`.
        self._impr.add_import_for_type(Import(module="warnings", name="warn"), warn)

        for type_ in (
            _IMPORTS
            + (_IMPORTS_VALIDATION_ERROR if has_validation_errors else [])
            + (
                _IMPORTS_SYNC_CLIENT
                if self._base_class is FastAPIClientBase
                else _IMPORTS_ASYNC_CLIENT
            )
        ):
            self._impr(type_)

        for type_ in _IMPORTS_TYPE_CHECKING:
            self._impr(type_, is_only_for_type_checking=True)

        def base_class_source_with_test_markers() -> str:
            source = getsource(self._base_class)
            if not self._add_test_markers:
                return source
            source_lines = source.splitlines()
            return (
                f"{source_lines[0]}\n"
                "    # TEST_MARKER_BEFORE_BOILERPLATE\n\n"
                f"{'\n'.join(source_lines[1:])}\n\n"
                "    # TEST_MARKER_AFTER_BOILERPLATE\n"
            )

        sources = [
            "# TEST_MARKER_BEFORE_BOILERPLATE\n" if self._add_test_markers else None,
            getsource(FastAPIClientExtensions),
            getsource(FastAPIClientResult),
            getsource(FastAPIClientValidationError) if has_validation_errors else None,
            (
                getsource(FastAPIClientHTTPValidationError)
                if has_validation_errors
                else None
            ),
            getsource(FastAPIClientNotDefaultStatusError),
            "FASTAPI_CLIENT_NOT_REQUIRED: Any = ...\n",
            "# TEST_MARKER_AFTER_BOILERPLATE\n" if self._add_test_markers else None,
            base_class_source_with_test_markers(),
        ]
        return "\n\n".join(self._idents.replace_in_code(s) for s in sources if s)


class _ImportCodeGenerator:
    def __init__(self, impr: ImportRegistry) -> None:
        self._impr = impr

    def generate(self) -> str:
        imports = set(self._impr.imports())

        imports_only_for_type_checking = set(
            self._impr.imports(only_for_type_checking=True)
        )
        if imports_only_for_type_checking:
            for import_ in imports_only_for_type_checking:
                imports.remove(import_)

            type_checking_import = Import(module="typing", name="TYPE_CHECKING")
            imports.add(type_checking_import)
            imports_only_for_type_checking.discard(type_checking_import)

        code = self._get_imports_code_for_import_block(imports)
        if imports_only_for_type_checking:
            code += "\nif TYPE_CHECKING:\n"
            for line in self._get_imports_code_for_import_block(
                imports_only_for_type_checking
            ).splitlines():
                code += f"    {line}\n"

        return code

    @classmethod
    def _get_imports_code_for_import_block(cls, imports: AbstractSet[Import]) -> str:
        imports_by_group = defaultdict[_ImportGroup, set[Import]](set)
        for import_ in imports:
            imports_by_group[cls._get_import_group(import_)].add(import_)

        lines = (
            cls._get_imports_code_for_import_group(imports_by_group[group])
            for group in _ImportGroup
        )
        return "\n".join(filter(None, lines))

    @classmethod
    @cache
    def _get_import_group(cls, import_: Import) -> _ImportGroup:
        top_level_module = import_.module.split(".", maxsplit=1)[0]
        if top_level_module in stdlib_module_names:
            return _ImportGroup.STDLIB
        spec = find_spec(top_level_module)
        if spec and spec.origin and "site-packages" in spec.origin:
            return _ImportGroup.SITE_PACKAGE
        return _ImportGroup.LOCAL

    @classmethod
    def _get_imports_code_for_import_group(cls, imports: AbstractSet[Import]) -> str:
        def alias_str(import_: Import) -> str:
            return f" as {import_.alias}" if import_.alias else ""

        imports_without_name = list[Import]()
        imports_with_name_by_module = defaultdict[str, list[Import]](list)
        for import_ in imports:
            if not import_.name:
                imports_without_name.append(import_)
            else:
                imports_with_name_by_module[import_.module].append(import_)

        imports_without_name.sort()

        code = ""
        for import_ in imports_without_name:
            if import_.module == "builtins" and import_.alias is None:
                continue
            code += f"import {import_.module}{alias_str(import_)}\n"
        for module in sorted(imports_with_name_by_module.keys()):
            imports_for_module = imports_with_name_by_module[module]
            if module == "builtins":
                imports_for_module = [
                    import_
                    for import_ in imports_for_module
                    if import_.alias is not None
                ]
            if not imports_for_module:
                continue

            imports_for_module.sort(
                key=lambda import_: (not import_.name.isupper(), import_.name)
            )

            if len(imports_for_module) == 1:
                import_ = imports_for_module[0]
                code += f"from {module} import {import_.name}{alias_str(import_)}\n"
            else:
                code += f"from {module} import (\n"
                code += "".join(
                    f"    {import_.name}{alias_str(import_)},\n"
                    for import_ in imports_for_module
                )
                code += ")\n"
        return code
