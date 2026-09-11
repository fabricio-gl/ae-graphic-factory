"""Static checks for generated After Effects ExtendScript."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List


def _without_strings_and_comments(source: str) -> str:
    output: List[str] = []
    i = 0
    state = "code"
    quote = ""
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if state == "code":
            if ch in ("'", '"'):
                state = "string"
                quote = ch
                output.append(" ")
            elif ch == "/" and nxt == "/":
                state = "line_comment"
                output.extend("  ")
                i += 1
            elif ch == "/" and nxt == "*":
                state = "block_comment"
                output.extend("  ")
                i += 1
            else:
                output.append(ch)
        elif state == "string":
            if ch == "\\":
                output.append(" ")
                if i + 1 < len(source):
                    output.append(" ")
                    i += 1
            elif ch == quote:
                state = "code"
                output.append(" ")
            else:
                output.append("\n" if ch == "\n" else " ")
        elif state == "line_comment":
            if ch == "\n":
                state = "code"
                output.append("\n")
            else:
                output.append(" ")
        else:
            if ch == "*" and nxt == "/":
                state = "code"
                output.extend("  ")
                i += 1
            else:
                output.append("\n" if ch == "\n" else " ")
        i += 1
    return "".join(output)


def _delimiter_errors(source: str) -> List[str]:
    source_without_target = re.sub(r"^\s*#target\s+aftereffects\s*$", "", source, count=1, flags=re.MULTILINE)
    clean = _without_strings_and_comments(source_without_target)
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: List[str] = []
    for ch in clean:
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack or stack.pop() != pairs[ch]:
                return ["Delimitadores no equilibrados."]
    return ["Delimitadores no equilibrados."] if stack else []


def _extract_config(source: str) -> Dict[str, Any]:
    match = re.search(r"var\s+CONFIG\s*=\s*(\{.*?\});\s*var\s+STATE", source, re.DOTALL)
    if not match:
        raise ValueError("No se encontró CONFIG serializado.")
    return json.loads(match.group(1))


def _node_syntax_error(source: str) -> str:
    node = shutil.which("node")
    if not node:
        return ""
    cleaned = re.sub(r"^\s*#target\s+aftereffects\s*$", "", source, count=1, flags=re.MULTILINE)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
            handle.write(cleaned)
            temp_path = handle.name
        result = subprocess.run([node, "--check", temp_path], capture_output=True, text=True, timeout=20, check=False)
        if result.returncode:
            message = (result.stderr or result.stdout).strip().splitlines()
            return "Node detectó sintaxis inválida: " + (message[-1] if message else "error desconocido")
        return ""
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


def validate_jsx(source: str, strict: bool = False) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    errors.extend(_delimiter_errors(source))
    if not re.search(r"^\s*#target\s+aftereffects", source):
        errors.append("Falta #target aftereffects.")

    required = (
        "app.project.items.addComp",
        "ADBE Root Vectors Group",
        "ADBE Gaussian Blur 2",
        "KeyframeEase",
        "ADBE Vector Rect Size",
        "addBoxText",
        "setTrackMatte",
        "addToMotionGraphicsTemplateAs",
        "app.project.save(aepFile)",
        "exportAsMotionGraphicsTemplate",
        "validateAssetFile(asset, relative)",
        "validateFootage(assets[i], STATE.footage[assets[i].id])",
        "motionGraphicsTemplateControllerCount",
        "STATE.aepSaved",
    )
    for token in required:
        if token not in source:
            errors.append("Falta la operación requerida: %s." % token)

    if re.search(r"\b(?:TODO|FIXME|PLACEHOLDER)\b|\[TODO", source, re.IGNORECASE):
        errors.append("El JSX contiene placeholders.")
    personal_path_pattern = (
        r"(?:[A-Za-z]:[\\/]+" + "Users" + r"[\\/]|/" + "Users" + r"/|/" + "home" + r"/)"
    )
    if re.search(personal_path_pattern, source, re.IGNORECASE):
        errors.append("El JSX contiene una ruta personal absoluta.")

    source_without_target = re.sub(r"^\s*#target\s+aftereffects\s*$", "", source, count=1, flags=re.MULTILINE)
    clean = _without_strings_and_comments(source_without_target)
    incompatible = {
        "let": r"\blet\s+",
        "const": r"\bconst\s+",
        "arrow function": r"=>",
        "template literal": r"`",
        "class": r"\bclass\s+",
        "async": r"\basync\s+",
        "optional chaining": r"\?\.",
    }
    for name, pattern in incompatible.items():
        if re.search(pattern, clean):
            errors.append("Sintaxis no compatible con ExtendScript: %s." % name)
    syntax_errors = _delimiter_errors(source) + [
        error for error in errors if "Sintaxis no compatible" in error or "#target" in error
    ]
    if "if (!property.isSpatial)" not in source or "PropertyValueType.TwoD" not in source:
        errors.append("Easing no distingue propiedades espaciales y dimensionalidad temporal.")
    if "if (STATE.controllersAdded < 1" not in source:
        errors.append("Falta el preflight de controladores reales antes de exportar MOGRT.")
    if "STATE.aepSaved = true" not in source or "rollbackUnsavedBuild" not in source:
        errors.append("Falta separar el guardado AEP del rollback de construcciones no guardadas.")

    save_index = source.find("app.project.save(aepFile)")
    export_index = source.find("exportAsMotionGraphicsTemplate")
    export_check = re.search(r"exportOk\s*=\s*[^;]*exportAsMotionGraphicsTemplate\([^;]+;\s*if\s*\(exportOk\s*!==\s*true\)", source, re.DOTALL)
    if save_index < 0 or export_index < 0 or save_index >= export_index:
        errors.append("El AEP debe guardarse antes de exportar el MOGRT.")
    if not export_check:
        errors.append("No se comprueba explícitamente el retorno de exportAsMotionGraphicsTemplate().")
    success_index = source.find("AEP y MOGRT generados correctamente")
    failure_check_index = source.find("if (exportOk !== true)")
    if success_index < 0 or failure_check_index < 0 or success_index <= failure_check_index:
        errors.append("El éxito debe anunciarse después de comprobar la exportación.")

    try:
        config = _extract_config(source)
        comp = config["spec"]["composition"]
        for key in ("duration_seconds", "frame_count", "fps", "width", "height"):
            if key not in comp:
                errors.append("CONFIG no incluye composition.%s." % key)
        max_frame = int(comp.get("frame_count", 0)) - 1
        spec = config["spec"]
        from .graphic_spec import validate_graphic_spec
        errors.extend(validate_graphic_spec(spec))
        for index, animation in enumerate(spec.get("animation", [])):
            limit = max_frame + 1 if animation.get("property") == "audio_gain_percent" else max_frame
            if animation.get("end_frame", limit + 1) > limit:
                errors.append("Keyframe %d excede la composición." % index)
            if animation.get("property") == "audio_gain_percent" and (
                "applyAudioGainAnimation(property, animation)" not in source or
                "ADBE Audio Levels" not in source or "20 * Math.log(percent / 100)" not in source
            ):
                errors.append("audio_gain_percent no está conectado a Audio Levels y conversión dB.")
            if animation.get("property") == "shape_size":
                if "applyShapeSizeAnimation" not in source or "ADBE Vector Rect Position" not in source:
                    errors.append("shape_size no está conectado a Rectangle Path > Size/Position.")
        if any(item.get("matte_id") for item in spec.get("elements", [])):
            if "TrackMatteType.ALPHA" not in source or "trackMatteLayer" not in source:
                errors.append("GRAPHIC_SPEC requiere Track Matte, pero el JSX no lo verifica.")
        if any(item.get("text_mode") == "paragraph" for item in spec.get("elements", [])):
            if "sourceRectAtTime" not in source:
                errors.append("El texto paragraph no incluye medición sourceRectAtTime().")
        if any(len(item.get("targets", [])) > 1 for item in spec.get("essential_graphics", [])):
            if "ADBE Color Control" not in source or "targetProperty.expression" not in source:
                errors.append("El control compartido no dispone de una propiedad maestra.")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append("CONFIG no es analizable: %s" % exc)

    function_defs = set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", clean))
    bare_calls = set(re.findall(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(", clean))
    allowed = {
        "function", "if", "for", "while", "switch", "catch", "new",
        "parseInt", "parseFloat", "isNaN", "isFinite", "String", "Number", "Boolean",
        "Date", "Error", "File", "Folder", "ImportOptions", "KeyframeEase", "alert",
    }
    unresolved = sorted(name for name in bare_calls if name not in function_defs and name not in allowed)
    if unresolved:
        errors.append("Funciones internas invocadas pero no definidas: %s." % ", ".join(unresolved))

    node_error = _node_syntax_error(source)
    if node_error:
        errors.append(node_error)
        syntax_errors.append(node_error)
    elif not shutil.which("node"):
        warnings.append("Node no está disponible; se omitió su comprobación sintáctica.")

    if strict and warnings:
        errors.extend("STRICT: " + warning for warning in warnings)
    syntax_status = "FAIL" if syntax_errors else ("PASS" if shutil.which("node") else "NOT_TESTED")
    return {"errors": errors, "warnings": warnings, "syntax_status": syntax_status}
