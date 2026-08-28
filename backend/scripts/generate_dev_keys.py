"""Генерация локальной RS256-пары для identity-service (dev, `make keys`, ADR 0011)."""

from pathlib import Path

from identity_service.infrastructure.security.keys import generate_private_key_pem

_SECRETS_DIR = Path(__file__).resolve().parent.parent / "secrets"
OUTPUT_PATH = _SECRETS_DIR / "identity_jwt_private_key.pem"


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(generate_private_key_pem())
    print(f"Ключ создан: {OUTPUT_PATH}")
    print(f"Укажи в .env: IDENTITY_JWT_PRIVATE_KEY_PATH={OUTPUT_PATH}")


if __name__ == "__main__":
    main()
