#!/usr/bin/env python3
"""Generate portable, synthetic acceptance media + GRAPHIC_SPEC + checked JSX."""
import argparse
import json
import sys
from pathlib import Path
from run_pipeline import run

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from media_fixtures import make_png, make_av_avi


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    work = args.workspace.resolve()
    if work.exists() and any(work.iterdir()):
        parser.error("Elige una carpeta nueva/vacía para conservar los resultados anteriores.")
    media = work / "input"
    media.mkdir(parents=True, exist_ok=True)
    make_png(media / "background.png", 1920, 1080)
    make_av_avi(media / "portrait.avi")
    analysis = json.loads((ROOT / "tests/fixtures/acceptance_av.json").read_text(encoding="utf-8"))
    request = "5 s, 1920x1080, 30 fps. Imagen de fondo, video vertical, entrada/salida, Gaussian Blur 80 editable y fundido de audio durante los últimos 15 fotogramas."
    result = run(request, work, reference=analysis)
    result["validation_kind"] = "OFFLINE_ONLY"
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["STATIC_CHECK_OK"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
