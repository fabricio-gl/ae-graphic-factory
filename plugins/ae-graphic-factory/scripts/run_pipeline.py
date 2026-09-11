#!/usr/bin/env python3
"""Run AE Graphic Factory through GRAPHIC_SPEC and static JSX validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from aegf.ae_jsx import generate_jsx
from aegf.graphic_spec import DURATION_QUESTION, DurationRequiredError, build_graphic_spec
from aegf.myfonts_adapter import build_identification_request
from aegf.orchestration import (
    OrchestrationError,
    analysis_from_capability,
    parse_orchestration_envelope,
    prepare_reference_analysis,
    stage_attachments,
)
from aegf.static_validation import validate_jsx


def _load_optional(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def run(
    request: str,
    workspace: Path,
    reference: Optional[Dict[str, Any]] = None,
    myfonts: Optional[Dict[str, Any]] = None,
    attachments: Optional[Iterable[Path]] = None,
    visual_analyzer: Optional[Callable[[list[str]], Dict[str, Any]]] = None,
    font_identifier: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    input_dir = workspace / "input"
    output_dir = workspace / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    status: Dict[str, Any] = {
        "GRAPHIC_SPEC_READY": "NOT_TESTED",
        "JSX_GENERATED": "NOT_TESTED",
        "STATIC_CHECK_OK": "NOT_TESTED",
        "GENERADO": "NOT_TESTED",
        "SINTAXIS_CORRECTA": "NOT_TESTED",
        "PRUEBA_ESTATICA_OK": "NOT_TESTED",
        "PRUEBA_AUTOMATIZADA_OK": "NOT_TESTED",
        "VALIDACIÓN_FUNCIONAL_REAL": "NOT_TESTED",
        "AE_RUNTIME_OK": "NOT_TESTED",
        "MOGRT_EXPORT_OK": "NOT_TESTED",
        "PREMIERE_IMPORT_OK": "NOT_TESTED",
        "PREMIERE_TIMELINE_OK": "NOT_TESTED",
        "question": None,
        "errors": [],
        "artifacts_written": [],
    }
    try:
        attachment_paths = [Path(item) for item in (attachments or [])]
        if attachment_paths:
            if reference is None:
                if visual_analyzer is None:
                    raise OrchestrationError(
                        "Las referencias deben analizarse con la capacidad visual de graphic-spec-builder."
                    )
                reference = analysis_from_capability(attachment_paths, visual_analyzer)
            reference, verified_paths = prepare_reference_analysis(attachment_paths, reference)
            stage_attachments(verified_paths, input_dir)
        typography = reference.get("typography", {}) if isinstance(reference, dict) else {}
        needs_font = isinstance(typography, dict) and bool(typography.get("requires_identification"))
        if needs_font and myfonts is None and font_identifier is not None:
            image = str(attachment_paths[0]) if attachment_paths else str(
                next(iter(reference.get("assets", [])), {}).get("source", "")
            )
            myfonts = font_identifier(build_identification_request(image, "identifica la tipografía editable"))
        spec = build_graphic_spec(request, reference, myfonts)
    except DurationRequiredError:
        status["GRAPHIC_SPEC_READY"] = "FAIL"
        status["question"] = DURATION_QUESTION
        _write_json(output_dir / "status.json", status)
        return status
    except (TypeError, ValueError, OSError) as exc:
        status["GRAPHIC_SPEC_READY"] = "FAIL"
        status["errors"].append(str(exc))
        _write_json(output_dir / "status.json", status)
        return status

    spec_path = output_dir / "GRAPHIC_SPEC.json"
    jsx_path = output_dir / "crear_grafico.jsx"
    _write_json(spec_path, spec)
    status["GRAPHIC_SPEC_READY"] = "PASS"
    status["artifacts_written"].append(str(spec_path))

    try:
        source = generate_jsx(spec)
        jsx_path.write_text(source, encoding="utf-8", newline="\n")
        status["JSX_GENERATED"] = "PASS"
        status["GENERADO"] = "PASS"
        status["artifacts_written"].append(str(jsx_path))
        result = validate_jsx(source, strict=True)
        status["SINTAXIS_CORRECTA"] = result["syntax_status"]
        if result["errors"]:
            status["STATIC_CHECK_OK"] = "FAIL"
            status["PRUEBA_ESTATICA_OK"] = "FAIL"
            status["errors"].extend(result["errors"])
        else:
            status["STATIC_CHECK_OK"] = "PASS"
            status["PRUEBA_ESTATICA_OK"] = "PASS"
    except (OSError, ValueError) as exc:
        status["JSX_GENERATED"] = "FAIL"
        status["STATIC_CHECK_OK"] = "FAIL"
        status["errors"].append(str(exc))

    _write_json(output_dir / "status.json", status)
    return status


def run_orchestrated(payload: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
    """Execute the internal skill handoff; users never prepare this envelope."""

    parsed = parse_orchestration_envelope(payload)
    return run(
        parsed["request"],
        workspace,
        parsed["visual_analysis"],
        parsed["myfonts_response"],
        parsed["attachments"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", help="Idea natural que debe incluir duración exacta.")
    parser.add_argument("--workspace", type=Path, default=Path.cwd() / "AE_Graphic_Lab")
    parser.add_argument(
        "--orchestrator-stdin",
        action="store_true",
        help="Lee por stdin el envelope interno producido por graphic-spec-builder.",
    )
    parser.add_argument("--reference-analysis", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--myfonts-response", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.orchestrator_stdin:
            result = run_orchestrated(json.load(sys.stdin), args.workspace)
        else:
            if not args.request:
                parser.error("--request es obligatorio fuera del modo orquestador.")
            result = run(
                args.request,
                args.workspace,
                _load_optional(args.reference_analysis),
                _load_optional(args.myfonts_response),
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("question"):
        return 2
    return 0 if result["STATIC_CHECK_OK"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
