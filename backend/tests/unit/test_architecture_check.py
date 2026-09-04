from pathlib import Path

import pytest

from scripts.check_architecture import main, scan

BACKEND = Path(__file__).parents[2]


def test_scan_reports_no_mixed_application_modules_after_support_migration() -> None:
    findings = scan(BACKEND)

    mixed = {
        finding.path.relative_to(BACKEND).as_posix()
        for finding in findings
        if finding.rule == "mixed-use-case-module"
    }

    assert mixed == set()


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


def test_scan_marks_mixed_application_modules_as_blocking(tmp_path: Path) -> None:
    application = tmp_path / "services/example/src/application"
    application.mkdir(parents=True)
    (application / "handlers.py").write_text(
        "class CreateThing:\n    pass\n\nclass ListThings:\n    pass\n",
        encoding="utf-8",
    )

    findings = scan(tmp_path)

    assert [(item.rule, item.blocking) for item in findings] == [
        ("mixed-use-case-module", True)
    ]


def test_scan_does_not_treat_camel_case_boundaries_as_read_markers(
    tmp_path: Path,
) -> None:
    command = tmp_path / "services/example/src/application/commands"
    command.mkdir(parents=True)
    (command / "change_ticket_status.py").write_text(
        "class ChangeTicketStatusCommand:\n    pass\n",
        encoding="utf-8",
    )

    findings = scan(tmp_path)

    assert findings == []


def test_scan_marks_cross_side_imports_as_blocking(tmp_path: Path) -> None:
    query = tmp_path / "services/example/src/application/queries"
    command = tmp_path / "services/example/src/application/commands"
    query.mkdir(parents=True)
    command.mkdir(parents=True)
    (command / "bad.py").write_text(
        "from application.queries.read_thing import ReadThingQuery\n",
        encoding="utf-8",
    )

    findings = scan(tmp_path)

    assert [(item.rule, item.blocking) for item in findings] == [
        ("cross-cqrs-import", True)
    ]


def test_scan_checks_package_facades_and_import_aliases(tmp_path: Path) -> None:
    application = tmp_path / "services/example/src/application"
    command = application / "commands"
    query = application / "queries"
    command.mkdir(parents=True)
    query.mkdir(parents=True)
    (application / "__init__.py").write_text(
        "from application.commands import CreateThingCommand\n"
        "from application.queries import ListThingsQuery\n",
        encoding="utf-8",
    )
    (command / "bad.py").write_text(
        "from application import queries\n", encoding="utf-8"
    )

    findings = scan(tmp_path)

    assert [(item.rule, item.blocking) for item in findings] == [
        ("mixed-use-case-module", True),
        ("cross-cqrs-import", True),
    ]


def test_strict_cli_fails_for_mixed_application_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = tmp_path / "services/example/src/application"
    application.mkdir(parents=True)
    (application / "handlers.py").write_text(
        "class CreateThing:\n    pass\n\nclass ListThings:\n    pass\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "sys.argv", ["check_architecture.py", "--root", str(tmp_path), "--strict"]
    )

    assert main() == 1
