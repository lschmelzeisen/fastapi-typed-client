import ast
from collections.abc import Collection, Iterator
from contextlib import suppress
from importlib import import_module
from pathlib import Path
from types import ModuleType, NoneType, UnionType
from typing import (
    Any,
    Literal,
    NamedTuple,
    Self,
    TypeAliasType,
    Union,
    get_args,
    get_origin,
)
from warnings import warn

from .string import dq_str_repr


class Import(NamedTuple):
    module: str
    name: str | None = None
    alias: str | None = None

    def ident(self) -> str:
        return self.alias or self.name or self.module.partition(".")[0]

    def is_same(self, other: Import) -> bool:
        return self.module == other.module and self.name == other.name

    def with_alias(self, alias: str | None) -> Self:
        return self.__class__(module=self.module, name=self.name, alias=alias)


class ImportUsage(NamedTuple):
    import_: Import
    usage: str


def load_import(module: str, name: str | None) -> Any:  # noqa: ANN401
    obj = import_module(module)
    if not name:
        return obj
    for name_part in name.split("."):
        obj = getattr(obj, name_part)
    return obj


def get_imports_from_module(module: ModuleType) -> Iterator[Import]:
    if not module.__file__:
        raise RuntimeError(f"Could not determine file path of module `{module}`.")
    path = Path(module.__file__)

    root = ast.parse(path.read_text(encoding="utf-8"), path)
    for node in ast.iter_child_nodes(root):
        if isinstance(node, ast.Import):
            for i in node.names:
                yield Import(module=i.name, name=None, alias=i.asname)
        elif isinstance(node, ast.ImportFrom):
            for i in node.names:
                yield Import(module=node.module or ".", name=i.name, alias=i.asname)


class ImportRegistry:
    # While this class is only supposed to operate on "types", we can not set the type
    # hint of `type_` to `type[Any]` as we also want to be able to handle various other
    # things like `Union`, `GenericAlias`, `TypeAliasType`, etc.

    def __init__(self) -> None:
        self._barriers = list[str]()  # Can't use set because we care about order.
        self._reserved_idents = set[str]()
        self._imports_by_ident = dict[str, Import]()
        self._import_usages_by_type = dict[Any, ImportUsage]()
        self._types_used_outside_of_type_checking = set[Any]()

    def imports(self, *, only_for_type_checking: bool = False) -> Collection[Import]:
        if only_for_type_checking:
            return {
                import_
                for type_, (import_, _usage) in self._import_usages_by_type.items()
                if type_ not in self._types_used_outside_of_type_checking
            }
        return self._imports_by_ident.values()

    def add_barrier(self, *barrier: str) -> None:
        for barrier_ in barrier:
            if barrier_ not in self._barriers:
                self._barriers.append(barrier_)

    def add_imports_from_module(self, module: ModuleType) -> None:
        for import_ in get_imports_from_module(module):
            self.add_import(import_)

    def add_reserved_ident(self, ident: str) -> None:
        if ident in self._imports_by_ident:
            raise RuntimeError(f"Identifier `{ident}` is already in use.")
        self._reserved_idents.add(ident)

    def add_import(
        self, import_: Import, *, is_only_for_type_checking: bool = False
    ) -> None:
        self.add_import_for_type(
            import_,
            type_=load_import(import_.module, import_.name),
            is_only_for_type_checking=is_only_for_type_checking,
        )

    def add_import_for_type(
        self,
        import_: Import,
        type_: Any,  # noqa: ANN401
        *,
        is_only_for_type_checking: bool = False,
    ) -> None:
        ident = import_.ident()
        if ident in self._reserved_idents:
            raise ValueError(f"Identifier `{ident}` has been reserved.")

        import_usage = ImportUsage(import_=import_, usage=ident)

        if not is_only_for_type_checking:
            self._types_used_outside_of_type_checking.add(type_)

        existing_import = self._imports_by_ident.get(ident)
        if import_ == existing_import:
            if type_ not in self._import_usages_by_type:
                self._import_usages_by_type[type_] = import_usage
            return
        if existing_import:
            raise ValueError(f"Import with name `{ident}` already exists.")

        self._imports_by_ident[ident] = import_
        self._import_usages_by_type[type_] = import_usage

    def add_import_usage_for_qualified_type(
        self,
        type_: Any,  # noqa: ANN401
        *,
        is_only_for_type_checking: bool = False,
    ) -> None:
        is_module = isinstance(type_, ModuleType)
        if hasattr(type_, "__qualname__"):
            if ".<locals>." in type_.__qualname__:
                raise ValueError(f"Can not handle local scope of `{type_!r}`.")
        elif not is_module and not isinstance(type_, TypeAliasType):
            raise ValueError(f"There is no qualified name for `{type_!r}`.")
        if not is_module and not type_.__module__:
            # Not sure how this can happen / what to do about it.
            raise ValueError(f"Module of `{type_!r}` is None.")

        if not is_only_for_type_checking:
            self._types_used_outside_of_type_checking.add(type_)

        import_usage = self._import_usages_by_type.get(type_)
        if import_usage:
            return

        import_usage = self._find_alias(
            self._find_import_usage(type_, self._find_shortest_import_for_type(type_))
            if not is_module
            else ImportUsage(
                import_=Import(module=type_.__name__), usage=type_.__name__
            )
        )
        self._imports_by_ident[import_usage.import_.ident()] = import_usage.import_
        self._import_usages_by_type[type_] = import_usage

    @staticmethod
    def _find_shortest_import_for_type(type_: Any) -> Import:  # noqa: ANN401
        module = type_.__module__
        name = type_.__name__
        # While `from {module} import {name}` will definitely work, try to find a
        # supermodule of `module` from which we can also import `name`.
        idx = -1
        while (idx := module.find(".", idx + 1)) != -1:
            supermodule = module[:idx]
            with suppress(ImportError, AttributeError):
                if type_ is load_import(supermodule, name):
                    return Import(module=supermodule, name=name)
        return Import(module=module, name=name)

    def _find_import_usage(self, type_: Any, import_: Import) -> ImportUsage:  # noqa: ANN401
        if not import_.name:
            raise RuntimeError(f"Received import without name: {import_}.")

        for barrier in self._barriers:
            if import_.module == barrier or import_.module.startswith(f"{barrier}."):
                break
        else:
            return ImportUsage(import_=import_, usage=import_.name)

        if "." in barrier:
            module, _, name = barrier.rpartition(".")
            usage = f"{import_.module.removeprefix(f'{module}.')}.{import_.name}"
        else:
            module = barrier
            name = None
            usage = f"{import_.module}.{import_.name}"

        import_ = Import(module=module, name=name)

        # While after `from {module} import {name}` we can definitely reach `type_` with
        # `usage`, try to find a shorter one by reducing it from the left.
        idx = len(usage)
        start_pos = (len(name) if name else len(module)) + 1
        while (idx := usage.rfind(".", start_pos, idx)) != -1:
            subusage = f"{name + '.' if name else ''}{usage[idx + 1 :]}"
            with suppress(ImportError, AttributeError):
                if type_ is load_import(module, subusage):
                    return ImportUsage(
                        import_=import_,
                        usage=subusage if name else f"{module}.{subusage}",
                    )
        return ImportUsage(import_=import_, usage=usage)

    def _find_alias(self, import_usage: ImportUsage) -> ImportUsage:
        import_ = import_usage.import_
        ident = import_.ident()

        alias = ident
        suffix = 2
        while alias in self._reserved_idents or (
            (existing_import := self._imports_by_ident.get(alias))
            and not existing_import.is_same(import_)
        ):
            alias = f"{ident}_{suffix}"
            suffix += 1

        if alias == ident:
            return import_usage
        return ImportUsage(
            import_=import_.with_alias(alias),
            usage=import_usage.usage.replace(ident, alias),
        )

    def get_usage(self, type_: Any, *, is_only_for_type_checking: bool = False) -> str:  # noqa: ANN401
        if type_ is None or type_ is NoneType:
            return "None"
        origin = get_origin(type_)
        if origin:
            args = get_args(type_)
            if origin is Literal:
                return f"{self.get_usage(origin)}[{', '.join(map(repr, args))}]"
            args_fmt = (self.get_usage(arg) for arg in args)
            if origin is Union or origin is UnionType:
                return " | ".join(args_fmt)
            return f"{self.get_usage(origin)}[{', '.join(args_fmt)}]"
        if type_ is type(Any):
            type_ = Any
        # Scuffed isinstance() check because we don't want to import
        # pydantic.fields.FieldInfo for users that don't need it.
        if (
            type_.__class__.__module__ == "pydantic.fields"
            and type_.__class__.__name__ == "FieldInfo"
        ):
            warn("Pydantic FieldInfo is not supported.", UserWarning, stacklevel=1)
            return "None"
        # type_ should be a qualified type by now.
        self.add_import_usage_for_qualified_type(
            type_, is_only_for_type_checking=is_only_for_type_checking
        )
        if type_ not in self._types_used_outside_of_type_checking:
            return dq_str_repr(self._import_usages_by_type[type_].usage)
        return self._import_usages_by_type[type_].usage

    def __call__(self, type_: Any, *, is_only_for_type_checking: bool = False) -> str:  # noqa: ANN401
        return self.get_usage(
            type_, is_only_for_type_checking=is_only_for_type_checking
        )
