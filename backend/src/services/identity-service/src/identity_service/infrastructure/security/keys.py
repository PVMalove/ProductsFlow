import base64
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from identity_service.settings import Settings


def load_private_key(path: str) -> rsa.RSAPrivateKey:
    with open(path, "rb") as key_file:
        data = key_file.read()
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError(f"Ожидается RSA-ключ, получен {type(key).__name__}")
    return key


def _b64url_uint(value: int) -> str:
    length = (value.bit_length() + 7) // 8 or 1
    raw = value.to_bytes(length, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def compute_kid(public_key: rsa.RSAPublicKey) -> str:
    """JWK thumbprint (RFC 7638) публичного ключа — стабилен между рестартами,
    одинаков у всех реплик, вычисляется из самого ключа без отдельного хранения."""
    numbers = public_key.public_numbers()
    thumbprint_input = {
        "e": _b64url_uint(numbers.e),
        "kty": "RSA",
        "n": _b64url_uint(numbers.n),
    }
    canonical = json.dumps(
        thumbprint_input, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_jwk(public_key: rsa.RSAPublicKey, kid: str) -> dict[str, str]:
    numbers = public_key.public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }


def validate_prod_key(settings: Settings) -> None:
    """Fail-fast: при APP_ENV=prod пустой/нечитаемый приватный ключ валит старт.
    При любом другом APP_ENV — дефолты допускаются (ADR 0011)."""
    if settings.app_env != "prod":
        return
    if not settings.identity_jwt_private_key_path:
        raise RuntimeError(
            "IDENTITY_JWT_PRIVATE_KEY_PATH не задан — обязателен при APP_ENV=prod"
        )
    try:
        load_private_key(settings.identity_jwt_private_key_path)
    except OSError as exc:
        raise RuntimeError(
            f"Не удалось прочитать приватный ключ "
            f"({settings.identity_jwt_private_key_path}): {exc}"
        ) from exc
