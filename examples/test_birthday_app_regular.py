from datetime import date

import pytest
from birthday_app import app, app_db
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    app_db.clear()
    return TestClient(app)


def test_register_birthday(client: TestClient) -> None:
    name = "Elvis"
    birthday = date(year=1935, month=1, day=8)

    register_response = client.post(
        "/birthday", json={"name": name, "birthday": f"{birthday:%Y-%m-%d}"}
    )
    register_response.raise_for_status()
    assert register_response.json() is True

    get_response = client.get(f"/birthday/{name}")
    get_response.raise_for_status()
    assert get_response.json() == {"name": name, "birthday": f"{birthday:%Y-%m-%d}"}


def test_unregistered_birthday(client: TestClient) -> None:
    response = client.get("/birthday/Elvis")
    assert response.status_code == 404
    assert response.json()["detail"] == "No birthday data for Elvis"
