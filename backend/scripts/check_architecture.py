"""Небольшая, не требующая зависимостей проверка архитектуры CQRS и границ слоёв.

Активный backend завершил миграцию на CQRS. Поэтому и направление
зависимостей, и смешанные command/query-модули — блокирующие нарушения.
Замороженный монолит находится вне корня сканирования и не затрагивается.
"""

from __future__ import annotations

import argparse
import ast
import re
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
_NAME_TOKEN = re.compile(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[0-9]+")


@dataclass(frozen=True)
class Finding:
    rule: str
    path: Path
    message: str
    blocking: bool
    line: int | None = None


def scan(root: Path) -> list[Finding]:
    """Возвращает детерминированные находки для файлов application и domain."""

    findings: list[Finding] = []
    for layer in ("domain", "application"):
        for path in sorted(root.rglob(f"src/{layer}/**/*.py")):
            findings.extend(_layer_import_findings(root, path, layer))
            if layer == "application":
                findings.extend(_cqrs_import_findings(path))
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
            dependency = next(
                (part for part in name.split(".") if part in forbidden), None
            )
            if dependency is not None:
                findings.append(
                    Finding(
                        rule="forbidden-layer-import",
                        path=path,
                        line=node.lineno,
                        blocking=True,
                        message=f"{layer} imports {dependency}",
                    )
                )
    return findings


def _import_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []

    names = [node.module] if node.module else []
    names.extend(
        f"{node.module}.{alias.name}" if node.module else alias.name
        for alias in node.names
    )
    return names


def _imported_cqrs_sides(node: ast.AST) -> set[str]:
    sides = {"commands", "queries"}
    return {
        side
        for name in _import_names(node)
        for side in sides
        if side in name.split(".")
    }


def _name_tokens(name: str) -> set[str]:
    """Разбивает CamelCase и snake_case имена перед сопоставлением с
    маркерами use case."""

    return {token.lower() for token in _NAME_TOKEN.findall(name)}


def _cqrs_import_findings(path: Path) -> list[Finding]:
    side = next((part for part in ("commands", "queries") if part in path.parts), None)
    if side is None:
        return []

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[Finding] = []
    opposite = "queries" if side == "commands" else "commands"
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if opposite in _imported_cqrs_sides(node):
            findings.append(
                Finding(
                    rule="cross-cqrs-import",
                    path=path,
                    line=node.lineno,
                    blocking=True,
                    message=f"{side} imports {opposite}",
                )
            )
    return findings


def _mixed_module_finding(path: Path) -> Finding | None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    writes = 0
    reads = 0
    imported_sides: set[str] = set()
    is_legacy_facade = path.stem == "handlers" or path.name.endswith("_handlers.py")
    for node in tree.body:
        imported_sides.update(_imported_cqrs_sides(node))
        if isinstance(node, ast.ClassDef):
            names = [node.name]
            if is_legacy_facade:
                names.extend(
                    child.name
                    for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                )
        elif is_legacy_facade and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            names = [node.name]
        else:
            names = []

        for name in names:
            tokens = _name_tokens(name)
            writes += bool(tokens.intersection(_WRITE_MARKERS))
            reads += bool(tokens.intersection(_READ_MARKERS))

    writes += "commands" in imported_sides
    reads += "queries" in imported_sides
    if writes and reads:
        return Finding(
            rule="mixed-use-case-module",
            path=path,
            blocking=True,
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
        help="fail when a blocking architecture violation is found",
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
