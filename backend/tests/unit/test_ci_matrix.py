import pytest

from scripts.ci_matrix import select_targets


def test_select_targets_keeps_an_independent_service() -> None:
    assert select_targets(["backend/services/catalog-service/src/api/main.py"]) == {
        "members": ["catalog-service"],
        "services": ["catalog-service"],
        "has_backend_changes": True,
    }


def test_select_targets_propagates_kernel_domain_to_all_dependents() -> None:
    assert select_targets(
        ["backend/libs/kernel-domain/src/kernel_domain/entity.py"]
    ) == {
        "members": [
            "kernel-domain",
            "kernel-platform",
            "identity-service",
            "catalog-service",
            "support-service",
        ],
        "services": ["identity-service", "catalog-service", "support-service"],
        "has_backend_changes": True,
    }


def test_select_targets_ignores_changes_outside_backend() -> None:
    assert select_targets(["docs/architecture.md"]) == {
        "members": [],
        "services": [],
        "has_backend_changes": False,
    }


@pytest.mark.parametrize(
    "path",
    [
        "backend/docker-compose.prod.yml",
        "backend/pyproject.toml",
        "backend/scripts/ci_matrix.py",
    ],
)
def test_select_targets_falls_back_to_every_member_for_shared_infrastructure(
    path: str,
) -> None:
    assert select_targets([path]) == {
        "members": [
            "kernel-domain",
            "kernel-platform",
            "observability",
            "test-support",
            "identity-service",
            "catalog-service",
            "support-service",
        ],
        "services": ["identity-service", "catalog-service", "support-service"],
        "has_backend_changes": True,
    }
