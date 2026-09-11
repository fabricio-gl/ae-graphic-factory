"""Dependency-free validation for the JSON Schema features used by GRAPHIC_SPEC."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    return True


def _resolve_ref(root: Dict[str, Any], reference: str) -> Dict[str, Any]:
    if not reference.startswith("#/"):
        raise ValueError("Solo se admiten referencias locales de schema: %s" % reference)
    value: Any = root
    for part in reference[2:].split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    return value


def validate_instance(instance: Any, schema: Dict[str, Any], root: Dict[str, Any] | None = None, path: str = "$") -> List[str]:
    root = root or schema
    if "$ref" in schema:
        return validate_instance(instance, _resolve_ref(root, schema["$ref"]), root, path)

    errors: List[str] = []
    for branch in schema.get("allOf", []):
        errors.extend(validate_instance(instance, branch, root, path))
    if "anyOf" in schema and all(validate_instance(instance, branch, root, path) for branch in schema["anyOf"]):
        errors.append("%s no coincide con ninguna alternativa." % path)
    if "not" in schema and not validate_instance(instance, schema["not"], root, path):
        errors.append("%s coincide con una alternativa prohibida." % path)
    if "if" in schema:
        branch = "else" if validate_instance(instance, schema["if"], root, path) else "then"
        if branch in schema:
            errors.extend(validate_instance(instance, schema[branch], root, path))
    if "oneOf" in schema:
        branch_errors = [validate_instance(instance, branch, root, path) for branch in schema["oneOf"]]
        matches = sum(1 for item in branch_errors if not item)
        if matches != 1:
            errors.append("%s debe coincidir con exactamente una alternativa del schema." % path)
            return errors
    if "const" in schema and instance != schema["const"]:
        errors.append("%s debe ser %r." % (path, schema["const"]))
    if "enum" in schema and instance not in schema["enum"]:
        errors.append("%s no pertenece al enum permitido." % path)

    expected = schema.get("type")
    if expected is not None:
        expected_types = expected if isinstance(expected, list) else [expected]
        if not any(_matches_type(instance, item) for item in expected_types):
            errors.append("%s tiene tipo inválido; se esperaba %s." % (path, expected_types))
            return errors

    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append("%s.%s es obligatorio." % (path, key))
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append("%s.%s no está permitido." % (path, key))
        for key, child_schema in properties.items():
            if key in instance:
                errors.extend(validate_instance(instance[key], child_schema, root, "%s.%s" % (path, key)))

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < int(schema["minItems"]):
            errors.append("%s requiere al menos %s elementos." % (path, schema["minItems"]))
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(instance):
                errors.extend(validate_instance(item, item_schema, root, "%s[%d]" % (path, index)))

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < int(schema["minLength"]):
            errors.append("%s es demasiado corto." % path)
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append("%s no cumple el patrón %s." % (path, schema["pattern"]))

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append("%s es menor que el mínimo." % path)
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append("%s supera el máximo." % path)
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append("%s debe superar el mínimo exclusivo." % path)
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            errors.append("%s debe ser menor que el máximo exclusivo." % path)
    return errors


def schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "schemas" / "graphic-spec.schema.json"


def validate_graphic_spec_schema(instance: Any) -> List[str]:
    schema = json.loads(schema_path().read_text(encoding="utf-8"))
    return validate_instance(instance, schema)
