from pathlib import Path

from scripts.check_architecture import scan

BACKEND = Path(__file__).parents[2]


def test_scan_reports_remaining_mixed_application_module() -> None:
    findings = scan(BACKEND)

    mixed = {
        finding.path.relative_to(BACKEND).as_posix()
        for finding in findings
        if finding.rule == "mixed-use-case-module"
    }

    assert mixed == {"services/support-service/src/application/ticket_use_cases.py"}


def test_scan_marks_forbidden_layer_imports_as_blocking(tmp_path: Path) -> None:
    application = tmp_path / "services/example/src/application/commands"
    application.mkdir(parents=True)
    (application / "bad.py").write_text(
        "from service.infrastructure.db.models import UserModel\n", encoding="utf-8"
    )

    findings = scan(tmp_path)

    assert [(item.rule, item.blocking) for item in findings] == [
        ("forbidden-layer-import", True)
    ]
