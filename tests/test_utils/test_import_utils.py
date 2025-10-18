import collections.abc
import json
from collections.abc import Collection, Sequence
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any, Literal, Union

import pytest
from pydantic import Field

from fastapi_typed_client._utils import (
    Import,
    ImportRegistry,
    get_imports_from_module,
    load_import,
)


def write_init_file(module_dir: Path, source: str = "") -> None:
    module_dir.mkdir(exist_ok=True)
    (module_dir / "__init__.py").write_text(source, encoding="utf-8")


pytestmark = [pytest.mark.usefixtures("tmp_import_path")]


@pytest.mark.parametrize("expected", ["abc", 123, True])
@pytest.mark.parametrize("name", ["baz", "baz.quux", "baz.quux.corge"])
@pytest.mark.parametrize("module", ["foo", "foo.bar"])
def test_load_import(module: str, name: str, expected: str, tmp_path: Path) -> None:
    module_dir = tmp_path
    module_split = module.split(".")
    for module_part in module_split:
        module_dir /= module_part
        write_init_file(module_dir)

    name_split = name.split(".")
    for name_part in name_split[:-1]:
        write_init_file(module_dir, f"from . import {name_part}")
        module_dir /= name_part
        write_init_file(module_dir)

    write_init_file(module_dir, f"{name_split[-1]} = {expected!r}")

    assert load_import(module, name) == expected


def test_get_imports_from_module(tmp_path: Path) -> None:
    source = (
        "import collections\n"
        "import collections.abc\n"
        "import collections.abc as foo\n"
        "from . import collections\n"
        "from . import collections as bar\n"
        "from collections import abc\n"
        "from collections import abc as baz\n"
        "from collections.abc import Collection\n"
        "from collections.abc import Collection as Quux\n"
    )
    module_dir = tmp_path / "module"
    write_init_file(module_dir, source)
    assert list(get_imports_from_module(import_module("module"))) == [
        Import(module="collections", name=None, alias=None),
        Import(module="collections.abc", name=None, alias=None),
        Import(module="collections.abc", name=None, alias="foo"),
        Import(module=".", name="collections", alias=None),
        Import(module=".", name="collections", alias="bar"),
        Import(module="collections", name="abc", alias=None),
        Import(module="collections", name="abc", alias="baz"),
        Import(module="collections.abc", name="Collection", alias=None),
        Import(module="collections.abc", name="Collection", alias="Quux"),
    ]


@pytest.mark.parametrize(
    ("type_", "expected_usage"),
    [
        (Any, "Any"),
        (str | None, "str | None"),
        (Union[int, bool], "int | bool"),  # noqa: UP007
        (Sequence[int], "Sequence[int]"),
        (dict[str, list[int]], "dict[str, list[int]]"),
        (Literal[123], "Literal[123]"),
        (Literal["foo"], "Literal['foo']"),
        (json, "json"),
        (collections.abc, "collections.abc"),
        (Annotated[int, None], "Annotated[int, None]"),
        pytest.param(
            Annotated[int, Field(gt=0)],
            "Annotated[int, lel]",
            marks=[
                pytest.mark.xfail(reason="Pydantic FieldInfo is not supported yet."),
                pytest.mark.filterwarnings("ignore:Pydantic FieldInfo.*"),
            ],
        ),
    ],
)
def test_get_usage_with_common_types(type_: Any, expected_usage: str) -> None:  # noqa: ANN401
    assert ImportRegistry().get_usage(type_) == expected_usage


def assert_imports_load_expected_types(
    imports: Collection[Import], usages: Sequence[str], expected_types: Sequence[Any]
) -> None:
    # Verify that imports and usages actually loads what we wanted to load.
    loads = SimpleNamespace()
    for import_ in imports:
        setattr(loads, import_.ident(), load_import(import_.module, import_.name))
    for expected_type, usage in zip(expected_types, usages, strict=True):
        type_ = loads
        for usage_part in usage.split("."):
            type_ = getattr(type_, usage_part, None)
        assert type_ == expected_type


@pytest.fixture
def nested_class_imports(tmp_path: Path) -> Any:  # noqa: ANN401
    def i(module: str, *names: str) -> str:
        return f"from {module} import {', '.join(names)}\n"

    def c(name: str) -> str:
        return f"class {name}:\n    pass\n"

    spec: dict[str, list[str]] = {
        "a": [i(".", "b"), i(".b", "C1", "D"), i(".b.d.e", "E2")],
        "a.b": [i(".c", "C1", "C2"), i(".d", "e", "D", "E1")],
        "a.b.c": [c("C1"), c("C2")],
        "a.b.d": [i(".e", "E1"), c("D")],
        "a.b.d.e": [c("E1"), c("E2"), c("E3")],
    }

    for module in sorted(spec.keys()):
        module_dir = tmp_path
        for module_part in module.split("."):
            module_dir /= module_part
        write_init_file(module_dir, "".join(spec[module]))

    result = SimpleNamespace()
    for module in sorted(spec.keys()):
        if "." not in module:
            setattr(result, module, import_module(module))
    return result


@pytest.mark.parametrize(
    ("barrier", "expected_usages"),
    [
        (None, ["C1", "C2", "D", "E1", "E2", "E3"]),
        # TODO: see how code can be changed to return `a.b.d.E3` for E3 in next case.
        ("a", ["a.C1", "a.b.C2", "a.D", "a.b.E1", "a.E2", "a.b.d.e.E3"]),
        ("a.b", ["C1", "b.C2", "D", "b.E1", "E2", "b.e.E3"]),
        ("a.b.c", ["C1", "C2", "D", "E1", "E2", "E3"]),
        ("a.b.d", ["C1", "C2", "D", "E1", "E2", "d.e.E3"]),
    ],
)
def test_get_usage_with_barrier(
    barrier: str | None,
    expected_usages: Sequence[str],
    nested_class_imports: Any,  # noqa: ANN401
) -> None:
    a = nested_class_imports.a
    types = [a.C1, a.b.C2, a.D, a.b.E1, a.E2, a.b.e.E3]

    import_registry = ImportRegistry()
    if barrier:
        import_registry.add_barrier(barrier)

    usages = [import_registry.get_usage(type_) for type_ in types]
    assert usages == expected_usages

    assert_imports_load_expected_types(import_registry.imports(), usages, types)


@pytest.mark.parametrize(
    ("num_conflicts", "expected_usages"),
    [
        (2, ["Conflict", "Conflict_2"]),
        (4, ["Conflict", "Conflict_2", "Conflict_3", "Conflict_4"]),
    ],
)
def test_get_usage_with_name_conflict(
    num_conflicts: int,
    expected_usages: Sequence[str],
    tmp_path: Path,
) -> None:
    types = list[Any]()
    for i in range(num_conflicts):
        module_dir = tmp_path / f"mod{i}"
        write_init_file(module_dir, "class Conflict:\n    pass\n")
        types.append(load_import(f"mod{i}", "Conflict"))

    import_registry = ImportRegistry()

    usages = list[str]()
    # Loop to confirm that earlier created aliases are returned on subsequent calls.
    for _ in range(3):
        usages = [import_registry.get_usage(type_) for type_ in types]
        assert usages == expected_usages
        assert len(import_registry.imports()) == num_conflicts

    assert_imports_load_expected_types(import_registry.imports(), usages, types)


def test_get_usage_with_reserver_name_conflict() -> None:
    import_registry = ImportRegistry()
    import_registry.add_reserved_ident(Collection.__name__)
    assert import_registry.get_usage(Collection) == f"{Collection.__name__}_2"


def test_get_usage_with_barrier_and_name_conflict(tmp_path: Path) -> None:
    write_init_file(tmp_path / "foo")
    write_init_file(
        tmp_path / "foo" / "bar", "class A:\n    pass\nclass B:\n    pass\n"
    )
    write_init_file(tmp_path / "baz")
    write_init_file(tmp_path / "baz" / "bar", "class A:\n    pass\n")

    types = [
        load_import("foo.bar", "A"),
        load_import("foo.bar", "B"),
        load_import("baz.bar", "A"),
    ]

    import_registry = ImportRegistry()
    import_registry.add_barrier("foo.bar", "baz.bar")

    usages = [import_registry.get_usage(type_) for type_ in types]
    assert usages == ["bar.A", "bar.B", "bar_2.A"]

    assert list(import_registry.imports()) == [
        Import(module="foo", name="bar", alias=None),
        Import(module="baz", name="bar", alias="bar_2"),
    ]
    assert_imports_load_expected_types(import_registry.imports(), usages, types)


def test_get_usage_with_is_only_for_type_checking() -> None:
    import_registry = ImportRegistry()
    assert (
        import_registry.get_usage(Sequence, is_only_for_type_checking=True)
        == '"Sequence"'
    )
    assert import_registry.get_usage(Sequence) == "Sequence"
    assert (
        import_registry.get_usage(Sequence, is_only_for_type_checking=True)
        == "Sequence"
    )


def test_imports_only_for_type_checking() -> None:
    sequence_import = Import(module=Sequence.__module__, name=Sequence.__name__)
    collection_import = Import(module=Collection.__module__, name=Collection.__name__)

    import_registry = ImportRegistry()

    assert not import_registry.imports()
    assert not import_registry.imports(only_for_type_checking=True)

    import_registry.get_usage(Sequence)

    assert list(import_registry.imports()) == [sequence_import]
    assert not import_registry.imports(only_for_type_checking=True)

    import_registry.get_usage(Collection, is_only_for_type_checking=True)

    assert sorted(import_registry.imports()) == [collection_import, sequence_import]
    assert list(import_registry.imports(only_for_type_checking=True)) == [
        collection_import
    ]

    import_registry.get_usage(Collection)

    assert sorted(import_registry.imports()) == [collection_import, sequence_import]
    assert not import_registry.imports(only_for_type_checking=True)
