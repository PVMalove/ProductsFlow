"""Select the CI package and Docker-image matrices from changed repository paths."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path

MEMBERS = (
    "kernel-domain",
    "kernel-platform",
    "observability",
    "test-support",
    "identity-service",
    "catalog-service",
    "support-service",
)
SERVICES = ("identity-service", "catalog-service", "support-service")

PACKAGE_PATHS = {
    "backend/libs/kernel-domain/": "kernel-domain",
    "backend/libs/kernel-platform/": "kernel-platform",
    "backend/libs/observability/": "observability",
    "backend/libs/test-support/": "test-support",
    "backend/services/identity-service/": "identity-service",
    "backend/services/catalog-service/": "catalog-service",
    "backend/services/support-service/": "support-service",
}
DEPENDENTS = {
    "kernel-domain": {
        "kernel-platform",
        "identity-service",
        "catalog-service",
        "support-service",
    },
    "kernel-platform": {"identity-service", "catalog-service", "support-service"},
    "observability": {"identity-service", "catalog-service"},
    "test-support": {"catalog-service", "support-service"},
}
SHARED_INFRASTRUCTURE_FILES = {
    ".github/workflows/ci.yml",
    "backend/Makefile",
    "backend/pyproject.toml",
    "backend/scripts/ci_matrix.py",
}


def select_targets(changed_paths: Iterable[str]) -> dict[str, object]:
    """Return affected package, image, and architecture-check targets."""
    paths = tuple(changed_paths)
    has_backend_changes = any(path.startswith("backend/") for path in paths)

    members: tuple[str, ...]
    if any(_is_shared_infrastructure(path) for path in paths):
        members = MEMBERS
    else:
        affected_members = {
            member
            for path in paths
            for prefix, member in PACKAGE_PATHS.items()
            if path.startswith(prefix)
        }
        members = tuple(
            member
            for member in MEMBERS
            if member in affected_members
            or any(
                member in DEPENDENTS.get(affected, set())
                for affected in affected_members
            )
        )

    return {
        "members": list(members),
        "services": [member for member in SERVICES if member in members],
        "has_backend_changes": has_backend_changes,
    }


def _is_shared_infrastructure(path: str) -> bool:
    return (
        path in SHARED_INFRASTRUCTURE_FILES
        or path.startswith("backend/docker-compose")
        and path.endswith((".yml", ".yaml"))
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--paths-json",
        default=os.environ.get("CHANGED_FILES", "[]"),
        help="JSON array of changed repository-relative paths",
    )
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    paths = json.loads(args.paths_json)
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        parser.error("--paths-json must be a JSON array of strings")

    targets = select_targets(paths)
    result = json.dumps(targets, separators=(",", ":"))
    print(result)

    if args.github_output:
        _write_github_outputs(args.github_output, targets)

    return 0


def _write_github_outputs(output_path: Path, targets: Mapping[str, object]) -> None:
    output_path.write_text(
        "\n".join(
            (
                f"members={json.dumps(targets['members'])}",
                f"services={json.dumps(targets['services'])}",
                f"has_backend_changes={str(targets['has_backend_changes']).lower()}",
            )
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
