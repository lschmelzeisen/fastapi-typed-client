# The contents of this file are copied into every folder created by the client_tester
# and async_client_tester fixtures, so that these types can be used by the FastAPI test
# apps we write in our tests.

from enum import IntEnum

from pydantic import BaseModel


class FooBarEnum(IntEnum):
    FOO = 123
    BAR = 456


class TextAndNum(BaseModel):
    text: str
    num: int


class TextAndNumDefault(TextAndNum):
    text: str = "foobarbaz"
    num: int = 4


TEXT_AND_NUM_DATA = [
    TextAndNum(text="foo", num=1),
    TextAndNum(text="bar", num=23),
    TextAndNum(text="baz", num=456),
]
