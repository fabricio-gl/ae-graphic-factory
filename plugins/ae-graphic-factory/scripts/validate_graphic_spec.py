#!/usr/bin/env python3
"""Validate GRAPHIC_SPEC JSON against schema and semantic invariants."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aegf.graphic_spec import validate_graphic_spec
from aegf.schema_validation import validate_graphic_spec_schema


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print("FAIL: %s" % exc)
        return 1

    errors = validate_graphic_spec_schema(spec) + validate_graphic_spec(spec)

    if errors:
        for error in errors:
            print("FAIL: " + error)
        return 1
    print("GRAPHIC_SPEC_READY=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
