"""Генерация локальной RS256-пары для identity-service (dev, `make keys`, ADR 0005)."""

from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from core.secrets import generate_private_key_pem

_SECRETS_DIR = Path(__file__).resolve().parent.parent / "secrets"
OUTPUT_PATH = _SECRETS_DIR / "identity_jwt_private_key.pem"
PUBLIC_OUTPUT_PATH = _SECRETS_DIR / "identity_jwt_public_key.pem"

def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    private_pem = generate_private_key_pem()
    OUTPUT_PATH.write_bytes(private_pem)
    
    # Generate public key from private key
    private_key = serialization.load_pem_private_key(private_pem, password=None, backend=default_backend())
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    PUBLIC_OUTPUT_PATH.write_bytes(public_pem)
    
    print(f"Ключ создан: {OUTPUT_PATH}")
    print(f"Публичный ключ создан: {PUBLIC_OUTPUT_PATH}")
    print(f"Укажи в .env: IDENTITY_JWT_PRIVATE_KEY_PATH={OUTPUT_PATH}")

if __name__ == "__main__":
    main()
