#!/usr/bin/env python3
"""Statically validate an AE Graphic Factory JSX."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aegf.static_validation import validate_jsx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsx", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        source = args.jsx.read_text(encoding="utf-8-sig")
    except OSError as exc:
        print("FAIL: %s" % exc)
        return 1
    result = validate_jsx(source, strict=args.strict)
    print("SINTAXIS_CORRECTA=" + result["syntax_status"])
    for warning in result["warnings"]:
        print("WARN: " + warning)
    if result["errors"]:
        for error in result["errors"]:
            print("FAIL: " + error)
        return 1
    print("STATIC_CHECK_OK=PASS")
    print("PRUEBA_ESTATICA_OK=PASS (no implica ejecución Adobe)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
