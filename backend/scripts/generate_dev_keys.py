"""Генерация локальной RS256-пары для identity-service (dev, `make keys`, ADR 0011)."""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_SECRETS_DIR = Path(__file__).resolve().parent.parent / "secrets"
OUTPUT_PATH = _SECRETS_DIR / "identity_jwt_private_key.pem"


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    OUTPUT_PATH.write_bytes(pem)
    print(f"Ключ создан: {OUTPUT_PATH}")
    print(f"Укажи в .env: IDENTITY_JWT_PRIVATE_KEY_PATH={OUTPUT_PATH}")


if __name__ == "__main__":
    main()
