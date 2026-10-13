from fastapi import FastAPI

from api.http.main import app


def test_service_exposes_fastapi_entrypoint() -> None:
    assert isinstance(app, FastAPI)
