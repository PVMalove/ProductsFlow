"""Small, dependency-free CQRS and layer-boundary architecture check.

The check is intentionally conservative: migration findings are reported so
that the current state remains visible, while only dependency-direction
violations fail ``--strict``.  Service migrations can therefore tighten the
gate one bounded context at a time.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

_FORBIDDEN_IMPORTS = {
    "domain": {"api", "application", "infrastructure", "fastapi", "sqlalchemy"},
    "application": {"api", "infrastructure", "fastapi", "sqlalchemy"},
}
_WRITE_MARKERS = (
    "activate",
    "change",
    "close",
    "create",
    "deactivate",
    "delete",
    "register",
    "send",
    "update",
    "upsert",
)
_READ_MARKERS = ("get", "list", "search", "find", "count", "audit")


@dataclass(frozen=True)
class Finding:
    rule: str
    path: Path
    message: str
    blocking: bool
    line: int | None = None


def scan(root: Path) -> list[Finding]:
    """Return deterministic findings for application and domain Python files."""

    findings: list[Finding] = []
    for layer in ("domain", "application"):
        for path in sorted(root.rglob(f"src/{layer}/*.py")):
            if path.name == "__init__.py":
                continue
            findings.extend(_layer_import_findings(root, path, layer))
            if layer == "application":
                finding = _mixed_module_finding(path)
                if finding is not None:
                    findings.append(finding)
    return sorted(findings, key=lambda item: (item.path.as_posix(), item.line or 0))


def _layer_import_findings(root: Path, path: Path, layer: str) -> list[Finding]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden = _FORBIDDEN_IMPORTS[layer]
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            top_level = name.split(".", maxsplit=1)[0]
            if top_level in forbidden:
                findings.append(
                    Finding(
                        rule="forbidden-layer-import",
                        path=path,
                        line=node.lineno,
                        blocking=True,
                        message=f"{layer} imports {top_level}",
                    )
                )
    return findings


def _mixed_module_finding(path: Path) -> Finding | None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    writes = 0
    reads = 0
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        name = node.name.lower()
        writes += any(marker in name for marker in _WRITE_MARKERS)
        reads += any(marker in name for marker in _READ_MARKERS)
    if writes and reads:
        return Finding(
            rule="mixed-use-case-module",
            path=path,
            blocking=False,
            message="contains both command-side and query-side use cases",
        )
    return None


def _format_finding(root: Path, finding: Finding) -> str:
    relative = finding.path.relative_to(root).as_posix()
    location = f"{relative}:{finding.line}" if finding.line else relative
    severity = "ERROR" if finding.blocking else "MIGRATION"
    return f"{severity} {finding.rule} {location} — {finding.message}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail when a blocking dependency-direction violation is found",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    findings = scan(root)
    for finding in findings:
        print(_format_finding(root, finding))
    if not findings:
        print("OK architecture boundaries and CQRS layout")
    return int(args.strict and any(finding.blocking for finding in findings))


if __name__ == "__main__":
    raise SystemExit(main())
