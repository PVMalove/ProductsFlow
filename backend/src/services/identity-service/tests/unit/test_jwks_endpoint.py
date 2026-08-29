import pytest
from fastapi.testclient import TestClient
from identity_service.infrastructure.security.keys import compute_kid, load_private_key
from identity_service.main import app
from identity_service.settings import settings

pytestmark = pytest.mark.usefixtures("configured_key_path")


def test_jwks_endpoint_returns_a_single_valid_rsa_key() -> None:
    with TestClient(app) as client:
        response = client.get("/.well-known/jwks.json")

    assert response.status_code == 200
    body = response.json()
    assert len(body["keys"]) == 1
    key = body["keys"][0]
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert key["use"] == "sig"
    assert key["n"] and key["e"]


def test_jwks_endpoint_kid_matches_the_signing_key_thumbprint() -> None:
    private_key = load_private_key(settings.identity_jwt_private_key_path)
    expected_kid = compute_kid(private_key.public_key())

    with TestClient(app) as client:
        response = client.get("/.well-known/jwks.json")

    assert response.json()["keys"][0]["kid"] == expected_kid


def test_jwks_endpoint_requires_no_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/.well-known/jwks.json", headers={})

    assert response.status_code == 200
