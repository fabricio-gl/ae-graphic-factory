#!/usr/bin/env python3
"""Run the editorial and non-editorial pipelines without launching Adobe."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from media_fixtures import make_av_avi, make_png  # noqa: E402
from run_pipeline import run  # noqa: E402
from aegf.graphic_spec import validate_graphic_spec  # noqa: E402
from aegf.schema_validation import validate_graphic_spec_schema  # noqa: E402
from aegf.static_validation import validate_jsx  # noqa: E402


OFFLINE_ADOBE_STATES = {
    "AE_RUNTIME_OK": "NOT_TESTED",
    "MOGRT_EXPORT_OK": "NOT_TESTED",
    "PREMIERE_IMPORT_OK": "NOT_TESTED",
    "PREMIERE_TIMELINE_OK": "NOT_TESTED",
}


def _fixture(name: str) -> Dict[str, Any]:
    return json.loads((ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8"))


def _load_artifacts(workspace: Path) -> tuple[Dict[str, Any], str]:
    output = workspace / "output"
    spec = json.loads((output / "GRAPHIC_SPEC.json").read_text(encoding="utf-8"))
    jsx = (output / "crear_grafico.jsx").read_text(encoding="utf-8")
    return spec, jsx


def _common_checks(result: Dict[str, Any], spec: Dict[str, Any], jsx: str) -> list[str]:
    errors = validate_graphic_spec_schema(spec) + validate_graphic_spec(spec)
    errors.extend(validate_jsx(jsx, strict=True)["errors"])
    for key in ("GRAPHIC_SPEC_READY", "JSX_GENERATED", "STATIC_CHECK_OK"):
        if result.get(key) != "PASS":
            errors.append("%s no terminó en PASS." % key)
    for key, expected in OFFLINE_ADOBE_STATES.items():
        if result.get(key) != expected:
            errors.append("%s debe ser %s en una prueba offline." % (key, expected))
    return errors


def _editorial_case(root: Path) -> Dict[str, Any]:
    sources = root / "sources"
    sources.mkdir(parents=True)
    video = make_av_avi(sources / "synthetic-video.avi", frames=180, fps=30, audio=False)
    capture = make_png(sources / "reference-card.png", width=960, height=540)
    analysis = _fixture("editorial_visual_analysis.json")
    workspace = root / "workspace"
    request = (
        "6 segundos. Fondo de video con blur, captura central con esquinas redondeadas, "
        "dos subrayados con reveal horizontal, entrada desde abajo y salida a la derecha."
    )
    result = run(
        request,
        workspace,
        attachments=[video, capture],
        visual_analyzer=lambda _paths: analysis,
    )
    spec, jsx = _load_artifacts(workspace)
    errors = _common_checks(result, spec, jsx)
    labels = {item["label"] for item in spec["elements"]}
    reveals = [item for item in spec["animation"] if item["property"] == "shape_size"]
    if spec["composition"]["duration_seconds"] != 6 or spec["composition"]["frame_count"] != 180:
        errors.append("El caso editorial no conserva 6 segundos a 30 fps.")
    if not {"BG_VIDEO", "BLUR", "CARD_CONTENT", "CARD_MATTE", "HL_01", "HL_02"}.issubset(labels):
        errors.append("El caso editorial no contiene la arquitectura visual esperada.")
    if len(reveals) != 2 or any(item.get("origin") != "left" or item["start_value"][0] != 0 for item in reveals):
        errors.append("Los dos highlights no tienen reveal shape_size desde el borde izquierdo.")
    if not any(item.get("matte_id") for item in spec["elements"]):
        errors.append("La captura editorial no declara Track Matte redondeado.")
    return {
        "name": "editorial",
        "status": "PASS" if not errors else "FAIL",
        "workspace": str(workspace),
        "errors": errors,
        "pipeline": result,
    }


def _non_editorial_case(root: Path) -> Dict[str, Any]:
    sources = root / "sources"
    sources.mkdir(parents=True)
    icon = make_png(sources / "icon-reference.png", width=64, height=64)
    analysis = _fixture("non_editorial_visual_analysis.json")
    workspace = root / "workspace"
    request = (
        "5 segundos. Panel informativo con icono, cifra y texto secundario; "
        "anima cada elemento de forma independiente."
    )
    result = run(
        request,
        workspace,
        attachments=[icon],
        visual_analyzer=lambda _paths: analysis,
    )
    spec, jsx = _load_artifacts(workspace)
    errors = _common_checks(result, spec, jsx)
    labels = {item["label"] for item in spec["elements"]}
    forbidden = [label for label in labels if label == "TITLE" or label.startswith("CARD") or label.startswith("HL_")]
    animated = {item["element"] for item in spec["animation"]}
    if spec.get("preset", {}).get("id") != "custom":
        errors.append("El caso no editorial debe recorrer la arquitectura custom.")
    if forbidden:
        errors.append("El caso no editorial depende de nombres editoriales: %s." % ", ".join(sorted(forbidden)))
    if not {"DATA_PANEL", "ICON", "METRIC", "CAPTION"}.issubset(labels):
        errors.append("El caso no editorial no contiene panel, icono, cifra y texto secundario.")
    if not {"data_panel", "info_icon", "metric", "caption"}.issubset(animated):
        errors.append("El caso no editorial no anima independientemente todos sus elementos.")
    return {
        "name": "non_editorial",
        "status": "PASS" if not errors else "FAIL",
        "workspace": str(workspace),
        "errors": errors,
        "pipeline": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    destination = args.workspace.resolve()
    if destination.exists() and any(destination.iterdir()):
        parser.error("Elige una carpeta nueva o vacía para los dos casos E2E.")
    destination.mkdir(parents=True, exist_ok=True)

    cases = [
        _editorial_case(destination / "editorial"),
        _non_editorial_case(destination / "non_editorial"),
    ]
    passed = all(case["status"] == "PASS" for case in cases)
    summary = {
        "kind": "OFFLINE_STATIC_ONLY",
        "status": "PASS" if passed else "FAIL",
        "cases": cases,
        "validation": {
            "GRAPHIC_SPEC_READY": "PASS" if passed else "FAIL",
            "JSX_GENERATED": "PASS" if passed else "FAIL",
            "STATIC_CHECK_OK": "PASS" if passed else "FAIL",
            **OFFLINE_ADOBE_STATES,
        },
    }
    (destination / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
