from pathlib import Path

from identity_service.infrastructure.security.keys import generate_private_key_pem


def write_rsa_key_file(path: Path) -> None:
    path.write_bytes(generate_private_key_pem())
