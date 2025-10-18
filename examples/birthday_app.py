from datetime import date

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel


class BirthdayData(BaseModel):
    name: str
    birthday: date


class GetBirthdayError(BaseModel):
    detail: str


app_db: dict[str, date] = {}  # Simple in-memory dict, just for example.
app = FastAPI(title="BirthdayApp")


@app.post("/birthday", status_code=status.HTTP_201_CREATED)
def register_birthday(data: BirthdayData) -> bool:
    app_db[data.name] = data.birthday
    return True


@app.get(
    "/birthday/{name}",
    responses={status.HTTP_404_NOT_FOUND: {"model": GetBirthdayError}},
)
def get_birthday(name: str) -> BirthdayData:
    if name not in app_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No birthday data for {name}"
        )
    return BirthdayData(name=name, birthday=app_db[name])
