# fastapi-typed-client

[![PyPI](https://img.shields.io/pypi/v/fastapi-typed-client)](https://pypi.org/project/fastapi-typed-client/)
[![Python 3.14](https://img.shields.io/pypi/pyversions/fastapi-typed-client)](https://pypi.org/project/fastapi-typed-client/)
[![License](https://img.shields.io/pypi/l/fastapi-typed-client)](./LICENSE)

Generate a fully-typed client for your [FastAPI](https://fastapi.tiangolo.com/) app with the Pydantic models from your code.

[Quickstart](#quickstart) • [Features](#features) • [Introduction](#introduction) • [Usage](#usage) • [Development](#development)  • [License](#license) • [Changelog](./CHANGELOG.md)

## Quickstart

If you are using [uv](https://docs.astral.sh/uv/) (recommended) and your FastAPI app is importable from `module.submodule` with name `app`:

```shell
uvx fastapi-typed-client generate module.submodule:app
```

Otherwise, do this (preferably in a [virtual environment](https://fastapi.tiangolo.com/virtual-environments/)):

```shell
pip install fastapi-typed-client
fastapi-typed-client generate module.submodule:app
```

This will generate a file called `fastapi_client.py` (or if your FastAPI app has a title: `<title>_client.py`). You can then use it like this:

```python
from module.submodule import app, YourPydanticModel
from fastapi_client import FastAPIClient

with FastAPIClient.from_app(app) as client:
    print(client.your_endpoint(your_param=YourPydanticModel(foo="bar")))
```

For help on available options, see:

```shell
fastapi-typed-client generate --help
```

## Features

Generates a client for your FastAPI app that:

- Has **full type annotations** for all endpoint parameters and combinations of status codes and response models
- Uses the **types and Pydantic models defined in your app code**
- Can be either **sync or async** (via the `--async` CLI option)
- Support for **path**, **query**, **header**, **body parameters** (plus experimental support for **cookie parameters**)
- Support for **streams of JSON objects** (experimental)
- Only depends on [Pydantic](https://pydantic.dev/), [HTTPX](https://www.python-httpx.org/), [`fastapi.encoders`](https://fastapi.tiangolo.com/reference/encoders/), and any Pydantic models that your app defines at runtime
- Generated code is **human-readable**, has **diff-friendly formatting**, **controllable import styles**, and is **designed to be checked into version control**
- Supports Python 3.14 and FastAPI >= 0.128.0 (open an [issue](https://github.com/lschmelzeisen/fastapi-typed-client/issues) if you need support for older versions)

## Introduction

The main use case of this tool is to write type-checked tests for FastAPI apps.

Let's take the following file `birthday_app.py` as an example of a simple FastAPI app:

```python
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
```

This app allows us to store and retrieve birthday information. Note that the `register_birthday` endpoint returns a status code of `201 Created` instead of the default `200 Ok`, and that the `get_birthday` endpoint returns a JSON object of shape `BirthdayData` on success or of shape `GetBirthdayError` with a `404 Not Found` on failure.

With regular [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/), we might test this app like so:

```python
import pytest
from birthday_app import app, app_db
from datetime import date
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
```

While this definitely tests the desired behavior of our app, this code is not ideal:

- Our tests hardcode the HTTP method and URL pattern that each endpoint expects and construct URLs with path parameters manually in multiple places.
- Our test code must be aware of how our app serializes and deserializes JSON. For example, how `birthday` is represented by FastAPI.
- Our tests need to specify what format each endpoint expects for its parameters. Path parameters need to be encoded in the URL, body parameters need to be gathered in a dict and passed to the `json` argument of `client.post`, whereas query parameters would need to be passed to the `params` argument. If we were to change the `alias` of a parameter, or if we refactor a body parameter to a query parameter, our tests would need to be updated to reflect this change.
- We use `response.raise_for_status()` to check assert that our endpoints did not return an error. However, this only checks for any `2xx` status code and silently would accept if `register_birthday` would erroneously return a `200 Ok` instead of a `201 Created`.
- There are no type-based guarantees for our test code. The type checker doesn't know what parameters are permissible to pass into an endpoint and what things they could return. For example, the type-checker can't know whether `response.json()["detail"]` is valid, nor can your IDE provide any type-based hints about it.

It's up to you whether you consider each of these points as downsides. For example, you can argue that you want your tests to duplicate such implementation details to protect against accidentally changing them. In any case, fastapi-typed-client allows us to address these concerns when desired.

First, we generate a fully-typed client for our FastAPI app with:

```shell
fastapi-typed-client generate birthday_app:app
```

This creates a file `birthday_app_client.py` (check out the [example generated client](./examples/birthday_app_client.py) if you want to see the actual generated code), which allows us to now write our tests as follows:

```python
import pytest
from birthday_app import BirthdayData, GetBirthdayError, app, app_db
from birthday_app_client import BirthdayAppClient
from collections.abc import Iterator
from datetime import date
from http import HTTPStatus
from typing import Literal, assert_type

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
```

Note that:

- We can now "call" our endpoints via simple methods like `client.register_birthday()` and `client.get_birthday()`. However, the same HTTP roundtrip and JSON serialization/deserialization as before takes place in the background.
- Our endpoints receive parameters with the _exact same_ types as we specified them in our original FastAPI app. In this case, we import `BirthdayData` from `birthday_app` and pass it to our endpoint.
- Everything is type-checked. The above code features a few `assert_type()` calls to demonstrate which types the type checker is aware of, but otherwise these are not needed. The generated client checks whether response data can be deserialized as expected, so our tests do not need to worry about this.
- Our tests do not repeat implementation details like HTTP methods and URL schemas.

### Comparison to OpenAPI client generators

Easy [client generation based on an app's OpenAPI spec](https://fastapi.tiangolo.com/advanced/generate-clients/) is one of the main advantages of FastAPI and fairly common.

The main difference between fastapi-typed-client and such tools (like [openapi-python-client](https://github.com/openapi-generators/openapi-python-client)) is that it reuses the types and Pydantic models from our application code instead of generating new ones.

This greatly simplifies writing tests, since we are aware of all the types from writing the app implementation. Additionally, it keeps diffs minimal when changing the app implementation and thus the generated clients.

## Usage

### Generating a client for a FastAPI app

To generate a new client for your FastAPI app from the command line:

```shell
fastapi-typed-client generate [OPTIONS] APP_IMPORT_STR
```

Where `APP_IMPORT_STR` is the FastAPI app import string in the format `module.submodule:app_name`. That is, your app needs to be importable as `from module.submodule import app_name`.

The following options are available (see also `fastapi-typed-client generate --help`):

- `--output-path PATH`: Path to write the generated client to. Defaults to `--title` (converted to snake_case) + `.py`.
- `--title TEXT`: Title for the class of the generated client. Defaults to the FastAPI app title (converted to UpperCamelCase) + `Client`.
- `--async`: Make generated client async.
- `--import-barrier MODULE`:  Module path(s) in format `module.submodule` to set as import barriers. Forces types in submodules to be imported through the barrier rather than directly. Can be specified multiple times.
- `--import-client-base`: Import the client base from `fastapi_typed_client.client` instead of writing it to the output file. Intended when working with multiple generated clients at once.
- `--raise-if-not-default-status`: Client methods will raise an exception by default if the respective endpoint does not return its default status code. With or without option, this can also be controlled at each method call with the `raise_if_not_default_status` parameter.  

Alternatively, for programmatic access, the function `generate_fastapi_typed_client()`, which can be imported from `fastapi_typed_client`, exposes the same functionality as the CLI command. Its parameters correspond one-to-one to the CLI options.

### Instantiating a generated client

The following assumes that your FastAPI app is available as `from fastapi_app import app` and your generated client class is named `FastAPIClient` in file `fastapi_client.py` (this may be changed using the `--output-path` and `--title` options).

To create an instance of the generated client you need to pass it an instance of a [`httpx.Client`](https://www.python-httpx.org/api/#client) (or of [`httpx.AsyncClient`](https://www.python-httpx.org/api/#asyncclient) if using `--async`) that connects to your `app`. See [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/) or [FastAPI Async Tests](https://fastapi.tiangolo.com/advanced/async-tests/) for how to do this. Then instantiate `FastAPIClient` like this:

```python
from fastapi_client import FastAPIClient

client = FastAPIClient(httpx_client)
# Do something with client.
```

For convenience, the classmethod `.from_app()` can be used to directly create a client for your `app`:

```python
from fastapi_app import app
from fastapi_client import FastAPIClient

with FastAPIClient.from_app(app) as client:
    pass  # Do something with client.
```

This approach uses FastAPI's [TestClient](https://fastapi.tiangolo.com/reference/testclient/) under the hood and thus triggers the [lifespan events](https://fastapi.tiangolo.com/advanced/testing-events/) of your FastAPI app. Because FastAPI does not have an async `TestClient`, this is _not_ the case if you use `--async`. Use something like [asgi-lifespan](https://github.com/florimondmanca/asgi-lifespan)'s `LifespanManager` to trigger lifespan events yourself if needed.

### Using a generated client

The generated `FastAPIClient` will contain one generated method for each endpoint defined by your FastAPI app.

That is, for an endpoint defined as follows:

```python
@app.get("/endpoint-url/{foo}")
def endpoint(
    foo: str,  # path parameters
    bar: int,  # query parameter
    baz: BazModel,  # body parameter (with custom Pydantic model)
) -> ResponseModel:  # custom Pydantic Model for response
    ...
```

The generated client will contain a method similar to the following:

```python
from fastapi_app import BazModel, ResponseModel
from http import HTTPStatus
from typing import Literal

class FastAPIClient:
    def endpoint(
        self,
        foo: str,
        bar: int,
        baz: BazModel,
        *,
        raise_if_not_default_status: bool = False,
        client_exts: FastAPIClientExtensions | None = None
    ) -> FastAPIClientResult[Literal[HTTPStatus.OK], ResponseModel]:
        ...
```

With an [client instance](#instantiating-a-generated-client) you can then just call this as `client.endpoint(foo="foo", bar=123, baz=BazModel())`. If you are unsure about the parameters and types of your generated client, it is helpful to review the generated `fastapi_client.py`. See [auxiliary classes](#auxiliary-classes), for documentation on classes like `FastAPIClientResult` and `FastAPIClientExtensions`.

For endpoints that can return errors (either because they define errors as [additional responses](https://fastapi.tiangolo.com/advanced/additional-responses/) or because they take parameters which can result in a Pydantic `ValidationError`) the return type of the generated endpoint method will be a union of all status codes with their respective response models.

If your set the `raise_if_not_default_status` parameter to `True` or use `--raise-if-not-default-status` when generating your client, the return type will just be the default status code (i.e., `200 Ok` or the one defined via `status_code` in the endpoint's decorator) with its response model. Should the endpoint return a different status code, a `FastAPIClientNotDefaultStatusError` will be raised, which contains the response status code and deserialized data.

There is experimental support for endpoints returning streams of JSON objects. The detection works by checking if the endpoint's response class is a subclass of both FastAPI's [StreamingResponse](https://fastapi.tiangolo.com/reference/responses/#fastapi.responses.StreamingResponse) and [JSONResponse](https://fastapi.tiangolo.com/reference/responses/#fastapi.responses.JSONResponse) classes. The generated method for this endpoint will then return an iterator over all JSON objects contained in the newline-delimited stream from the endpoint. It can be used like this (see the [test for this feature](./tests/test_core/test_streaming_json_response.py) for an example):

```python
for item in client.your_streaming_endpoint().data:
    print(item.field)
```

For now, this detection of streaming JSON output is only available for the default response of an endpoint and not for additional responses.

### Auxiliary classes

The following auxiliary classes are either included in the generated `fastapi_client.py` file or imported from `fastapi_typed_client.client` if using `--import-client-base`.

#### `FastAPIClientResult[Status: http.HTTPStatus, Model]`
  
Parameterized type that is returned by each endpoint method. The generic parameters `Status` and `Model` specify status code and response model of each endpoint in the type system. Endpoint's with [additional responses](https://fastapi.tiangolo.com/advanced/additional-responses/) return a union of specializations of this type. 

Instance attributes:

- `status: Status`: The [`http.HTTPStatus`](https://docs.python.org/3/library/http.html#http.HTTPStatus) of the response
- `data: Model`: The deserialized response data
- `model: type[Model]`: The type used to deserialize the response data
- `response: Response`: The raw `httpx.Response` object

#### `FastAPIClientNotDefaultStatusError`
  
Exception raised when using `raise_if_not_default_status=True` or `--raise-if-not-default-status` and an endpoint returns a non-default status code.

Instance attributes:

- `default_status: HTTPStatus`: The expected status code
- `result: FastAPIClientResult`: The actual result received

#### `FastAPIClientHTTPValidationError` and `FastAPIClientValidationError`
  
Pydantic models for deserializing `422 Unprocessable Entity` responses from your FastAPI app.

Instance attributes of `FastAPIClientHTTPValidationError`:

- `detail: Sequence[FastAPIClientValidationError]`: List of validation errors

Instance attributes of `FastAPIClientValidationError`:

- `loc: Sequence[str | int]`: Location of the error
- `msg: str`: Error message
- `type: str`: Error type

#### `FastAPIClientExtensions`
  
TypedDict for passing additional options via the `client_exts` parameter to each endpoint. Currently only supports the following field:

- `timeout: float | tuple[float | None, float | None, float | None, float | None] | httpx.Timeout | None`: Request timeout, directly passed to [`httpx.Client.request`](https://www.python-httpx.org/api/#client)

### Current limitations

The following FastAPI features are not yet supported:

- [WebSockets](https://fastapi.tiangolo.com/advanced/websockets/) endpoints
- Endpoints with [form data](https://fastapi.tiangolo.com/tutorial/request-forms/) or [file upload](https://fastapi.tiangolo.com/tutorial/request-files/) parameters
- Endpoints that can be reached via more than one HTTP method
- Endpoints with duplicate parameter names (e.g., a query and a header parameter with the same name)
- Endpoints using any of `response_model_include`, `response_model_exclude`, `response_model_by_alias`, `response_model_exclude_unset`, `response_model_exclude_defaults`, or `response_model_exclude_none`
- Endpoints with `FileResponse`, `HTMLResponse`, `PlainTextResponse`, `RedirectResponse` or a custom response class

## Development

Contributions welcome! Feel free to create [issues](https://github.com/lschmelzeisen/fastapi-typed-client/issues) and [pull requests](https://github.com/lschmelzeisen/fastapi-typed-client/pulls).

There is a `Makefile` with helpers for how to run the development tools ([uv](https://docs.astral.sh/uv/), [Ruff](https://docs.astral.sh/ruff/), [Pyrefly](https://pyrefly.org/), [pytest](https://docs.pytest.org)). Run `make help` for an overview of available commands.

## License

Licensed under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).