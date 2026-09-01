from fastapi import FastAPI

from presentation.main import app


def test_service_exposes_fastapi_entrypoint() -> None:
    assert isinstance(app, FastAPI)
