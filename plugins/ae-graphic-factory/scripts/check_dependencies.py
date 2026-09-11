#!/usr/bin/env python3
"""Check only dependencies that are observable from this local process.

Connected apps and skills are discovered by the Codex runtime. The
graphic-spec-builder skill may pass the names it actually sees with
--capability; absence of that snapshot is NOT_TESTED, never a filesystem-based
false negative.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def dependency_report(capabilities: Iterable[str] = ()) -> Dict[str, Any]:
    observed = {item.strip() for item in capabilities if item.strip()}
    local_files = {
        "plugin_manifest": PLUGIN_ROOT / ".codex-plugin" / "plugin.json",
        "graphic_spec_schema": PLUGIN_ROOT / "schemas" / "graphic-spec.schema.json",
        "graphic_spec_skill": PLUGIN_ROOT / "skills" / "graphic-spec-builder" / "SKILL.md",
        "ae_jsx_skill": PLUGIN_ROOT / "skills" / "ae-graphic-jsx-creator" / "SKILL.md",
    }
    local = {
        name: {"status": "PASS" if path.is_file() else "FAIL", "path": str(path)}
        for name, path in local_files.items()
    }
    runtime_names = {
        "myfonts": {
            "mcp__codex_apps__myfonts_detect_font_regions",
            "mcp__codex_apps__myfonts_get_region",
            "mcp__codex_apps__myfonts_predict_font",
        },
        "premiere-jsx-script-creator": {"premiere-jsx-script-creator"},
    }
    runtime = {}
    for name, aliases in runtime_names.items():
        runtime[name] = {
            "status": "PASS" if observed.intersection(aliases) else "NOT_TESTED",
            "discovery": "Codex runtime capability registry",
        }
    return {
        "local": local,
        "runtime_capabilities": runtime,
        "note": (
            "Apps y skills conectadas no se buscan en rutas privadas. "
            "La skill transmite el snapshot oficial de capacidades cuando está disponible."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        help="Nombre exacto observado por el registro de capacidades de la sesión.",
    )
    args = parser.parse_args()
    report = dependency_report(args.capability)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item["status"] == "PASS" for item in report["local"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
