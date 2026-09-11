#!/usr/bin/env python3
"""Run clean-source release checks and optionally create a verified plugin ZIP."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".git", "dist", "validation"}
EXCLUDED_NAMES = {".env", "credentials.json", "secrets.json", "id_rsa"}
EXCLUDED_SUFFIXES = {".log", ".pyc", ".pyo", ".key", ".pem"}
TEXT_SUFFIXES = {".json", ".md", ".py", ".js", ".jsx", ".yaml", ".yml"}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: List[str]) -> Dict[str, Any]:
    process = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    print(("PASS" if process.returncode == 0 else "FAIL") + " | " + subprocess.list2cmdline(command[3:]))
    return {
        "command": command,
        "exit_code": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }


def _package_files() -> List[Path]:
    files: List[Path] = []
    for source in ROOT.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if source.name.lower() in EXCLUDED_NAMES or source.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        files.append(source)
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def _source_errors(files: Iterable[Path]) -> List[str]:
    errors: List[str] = []
    personal_windows = re.compile(r"[A-Za-z]:[\\/]+" + "Users" + r"[\\/]", re.IGNORECASE)
    personal_unix = re.compile(r"/(?:" + "Users" + "|" + "home" + r")/")
    for source in files:
        relative = source.relative_to(ROOT).as_posix()
        try:
            if source.suffix == ".py":
                ast.parse(source.read_text(encoding="utf-8-sig"), filename=str(source))
        except SyntaxError as error:
            errors.append("Sintaxis Python inválida en %s: %s" % (relative, error))
        if source.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            content = source.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            errors.append("Archivo textual no decodificable como UTF-8: %s" % relative)
            continue
        if personal_windows.search(content) or personal_unix.search(content):
            errors.append("Ruta personal hard-coded en %s." % relative)
        scaffold_markers = ("[" + "TO" + "DO:", "[" + "PLACE" + "HOLDER:")
        if any(marker.lower() in content.lower() for marker in scaffold_markers):
            errors.append("Placeholder pendiente en %s." % relative)
    return errors


def _create_package(output: Path, files: List[Path]) -> Dict[str, Any]:
    if output.exists():
        raise RuntimeError("No se sobrescribe un ZIP existente: %s" % output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in files:
            relative = source.relative_to(ROOT).as_posix()
            archive.write(source, "ae-graphic-factory/" + relative)

    with zipfile.ZipFile(output) as archive:
        damaged = archive.testzip()
        names = archive.namelist()
        bad_names = [
            name for name in names
            if name.startswith(("/", "\\"))
            or re.match(r"^[A-Za-z]:", name)
            or ".." in name.replace("\\", "/").split("/")
            or any(part in EXCLUDED_PARTS for part in name.replace("\\", "/").split("/"))
            or Path(name).name.lower() in EXCLUDED_NAMES
            or Path(name).suffix.lower() in EXCLUDED_SUFFIXES
        ]
        if damaged or bad_names:
            raise RuntimeError("El ZIP final no superó la inspección: %s" % (damaged or ", ".join(bad_names)))
    return {
        "path": str(output),
        "sha256": _digest(output),
        "entry_count": len(names),
        "crc": "PASS",
        "content_policy": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-creator", type=Path, help="Raíz de plugin-creator para validar el manifiesto.")
    parser.add_argument("--skill-creator", type=Path, help="Raíz de skill-creator para validar las skills.")
    parser.add_argument("--capability", action="append", default=[], help="Capacidad observada por el runtime Codex.")
    parser.add_argument("--package", action="store_true")
    parser.add_argument("--output", type=Path, help="Ruta nueva para el ZIP; requiere --package.")
    args = parser.parse_args()
    if args.output and not args.package:
        parser.error("--output requiere --package.")

    destination = ROOT / "validation"
    destination.mkdir(exist_ok=True)
    python = [sys.executable, "-X", "utf8", "-B"]

    with tempfile.TemporaryDirectory(prefix="aegf-release-") as temporary:
        e2e = Path(temporary) / "offline-e2e"
        commands = [
            python + ["-m", "unittest", "discover", "-s", "tests", "-v"],
            python + ["scripts/run_offline_e2e.py", "--workspace", str(e2e)],
            python + ["scripts/check_dependencies.py"] + [
                value for capability in args.capability for value in ("--capability", capability)
            ],
            python + ["scripts/validate_graphic_spec.py", str(e2e / "editorial/workspace/output/GRAPHIC_SPEC.json")],
            python + ["scripts/validate_ae_jsx.py", str(e2e / "editorial/workspace/output/crear_grafico.jsx"), "--strict"],
            python + ["scripts/validate_graphic_spec.py", str(e2e / "non_editorial/workspace/output/GRAPHIC_SPEC.json")],
            python + ["scripts/validate_ae_jsx.py", str(e2e / "non_editorial/workspace/output/crear_grafico.jsx"), "--strict"],
        ]
        if args.plugin_creator:
            commands.append(python + [str(args.plugin_creator / "scripts/validate_plugin.py"), str(ROOT)])
        if args.skill_creator:
            commands.extend([
                python + [str(args.skill_creator / "scripts/quick_validate.py"), "skills/graphic-spec-builder"],
                python + [str(args.skill_creator / "scripts/quick_validate.py"), "skills/ae-graphic-jsx-creator"],
            ])
        reports = [_run(command) for command in commands]

    files = _package_files()
    errors = _source_errors(files)
    failed_commands = [report for report in reports if report["exit_code"] != 0]
    passed = not failed_commands and not errors
    combined_test_output = reports[0]["stdout"] + reports[0]["stderr"]
    test_match = re.search(r"Ran\s+(\d+)\s+tests?", combined_test_output)
    test_count = int(test_match.group(1)) if test_match else None
    manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    result: Dict[str, Any] = {
        "version": manifest["version"],
        "commands": reports,
        "source_errors": errors,
        "unit_tests": {
            "pass": test_count if passed and test_count is not None else 0,
            "fail": 0 if passed else len(failed_commands),
        },
        "release_checks": {"pass": len(reports) - len(failed_commands), "fail": len(failed_commands)},
        "validation": {
            "GRAPHIC_SPEC_READY": "PASS" if passed else "FAIL",
            "JSX_GENERATED": "PASS" if passed else "FAIL",
            "STATIC_CHECK_OK": "PASS" if passed else "FAIL",
            "AE_RUNTIME_OK": "NOT_TESTED",
            "MOGRT_EXPORT_OK": "NOT_TESTED",
            "PREMIERE_IMPORT_OK": "NOT_TESTED",
            "PREMIERE_TIMELINE_OK": "NOT_TESTED",
        },
    }

    if args.package and passed:
        base_version = str(manifest["version"]).split("+", 1)[0]
        output = (args.output or (ROOT / "dist" / ("ae-graphic-factory-" + base_version + ".zip"))).resolve()
        result["package"] = _create_package(output, files)
    elif args.package:
        errors.append("No se empaquetó porque existen comprobaciones fallidas.")

    (destination / "release-checks.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (destination / "test-commands.log").write_text(
        "\n\n".join(
            "$ " + subprocess.list2cmdline(report["command"]) + "\nexit=" + str(report["exit_code"]) + "\n" +
            report["stdout"] + report["stderr"]
            for report in reports
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "unit_tests": result["unit_tests"],
        "release_checks": result["release_checks"],
        "validation": result["validation"],
        "package": result.get("package"),
        "source_errors": errors,
    }, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
