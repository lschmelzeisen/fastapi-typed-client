import pytest

from fastapi_typed_client._utils import (
    dq_str_repr,
    indent,
    to_constant_case,
    to_snake_case,
    to_upper_camel_case,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("MyApp", "MyApp"),
        ("FastAPI", "FastAPI"),
        ("FastAPI_Client", "FastAPIClient"),
        ("app-client", "AppClient"),
        ("MyApp FastAPI error", "MyAppFastAPIError"),
    ],
)
def test_to_upper_camel_case(text: str, expected: str) -> None:
    assert to_upper_camel_case(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("MyApp", "my_app"),
        ("FastAPI", "fast_api"),
        ("FastAPI_Client", "fast_api_client"),
        ("app-client", "app_client"),
        ("MyApp FastAPI error", "my_app_fast_api_error"),
    ],
)
def test_to_snake_case(text: str, expected: str) -> None:
    assert to_snake_case(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("MyApp", "MY_APP"),
        ("FastAPI", "FAST_API"),
        ("FastAPI_Client", "FAST_API_CLIENT"),
        ("app-client", "APP_CLIENT"),
        ("MyApp FastAPI error", "MY_APP_FAST_API_ERROR"),
    ],
)
def test_to_constant_case(text: str, expected: str) -> None:
    assert to_constant_case(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("foo", '"foo"'),
        ("foo'bar", '"foo\'bar"'),
        ('foo"bar', '"foo\\"bar"'),
    ],
)
def test_dq_str_repr(text: str, expected: str) -> None:
    assert dq_str_repr(text) == expected


@pytest.mark.parametrize(
    ("text", "depth", "expected"),
    [
        ("foo", 1, "    foo\n"),
        ("foo\nbar\n", 2, "        foo\n        bar\n"),
        ("", 3, ""),
    ],
)
def test_indent(text: str, depth: int, expected: str) -> None:
    assert indent(text, depth) == expected
