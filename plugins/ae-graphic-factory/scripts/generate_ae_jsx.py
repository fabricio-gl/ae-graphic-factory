#!/usr/bin/env python3
"""Generate a self-contained After Effects JSX from GRAPHIC_SPEC."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aegf.ae_jsx import generate_jsx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        source = generate_jsx(spec)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(source, encoding="utf-8", newline="\n")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("FAIL: %s" % exc)
        return 1
    print("JSX_GENERATED=PASS")
    print("GENERADO=PASS (no implica ejecución Adobe)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
