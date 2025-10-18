from collections.abc import Iterator
from datetime import date
from http import HTTPStatus
from typing import Literal, assert_type

import pytest
from birthday_app import BirthdayData, GetBirthdayError, app, app_db
from birthday_app_client import BirthdayAppClient


@pytest.fixture
def client() -> Iterator[BirthdayAppClient]:
    app_db.clear()
    with BirthdayAppClient.from_app(app) as client:
        yield client


def test_register_birthday(client: BirthdayAppClient) -> None:
    name = "Elvis"
    birthday = date(year=1935, month=1, day=8)

    register_response = client.register_birthday(
        BirthdayData(name=name, birthday=birthday), raise_if_not_default_status=True
    )
    assert_type(register_response.status, Literal[HTTPStatus.CREATED])
    assert_type(register_response.data, bool)
    assert register_response.data is True

    get_response = client.get_birthday(name, raise_if_not_default_status=True)
    assert_type(get_response.status, Literal[HTTPStatus.OK])
    assert_type(get_response.data, BirthdayData)
    assert get_response.data == BirthdayData(name=name, birthday=birthday)


def test_unregistered_birthday(client: BirthdayAppClient) -> None:
    response = client.get_birthday("Elvis")
    assert response.status == HTTPStatus.NOT_FOUND
    assert_type(response.data, GetBirthdayError)
    assert response.data.detail == "No birthday data for Elvis"
