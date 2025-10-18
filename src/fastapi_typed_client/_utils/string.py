import json
import re


def _split_text(text: str) -> list[str]:
    return re.split(r"-+|_+|\s+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", text)


def to_upper_camel_case(text: str) -> str:
    return "".join(word[0].upper() + word[1:] for word in _split_text(text))


def to_snake_case(text: str) -> str:
    return "_".join(word.lower() for word in _split_text(text))


def to_constant_case(text: str) -> str:
    return "_".join(word.upper() for word in _split_text(text))


def dq_str_repr(text: str) -> str:
    """Like repr() for strings, but encloses them in double quotes."""
    return json.dumps(text)


def indent(text: str, depth: int = 1) -> str:
    if not text:
        return ""
    return "".join(f"{'    ' * depth}{line}\n" for line in text.splitlines())
