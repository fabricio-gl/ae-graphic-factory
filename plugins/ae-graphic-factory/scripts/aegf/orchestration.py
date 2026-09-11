"""Boundary between Codex visual/app capabilities and the offline Python core.

Python deliberately does not pretend to perform semantic vision or call a
connected app. The graphic-spec-builder skill supplies those results through
this small, versioned envelope.
"""

from __future__ import annotations

import copy
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".psd", ".svg", ".tif", ".tiff", ".webp"}
VIDEO_EXTENSIONS = {".avi", ".m4v", ".mov", ".mp4", ".mxf", ".webm"}
ORCHESTRATION_VERSION = "1.0"


class OrchestrationError(ValueError):
    """Raised when the skill-to-script handoff is incomplete or unsafe."""


def _media_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    raise OrchestrationError("Tipo de referencia no soportado: %s" % path.name)


def _safe_id(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").lower()
    if not cleaned or not cleaned[0].isalpha():
        cleaned = fallback
    return cleaned


def _role_for(path: Path, kind: str, analysis: Dict[str, Any]) -> str:
    roles = analysis.get("asset_roles", {})
    if isinstance(roles, dict):
        for key in (str(path), path.name):
            value = roles.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    existing = analysis.get("assets", [])
    if isinstance(existing, list):
        for asset in existing:
            if isinstance(asset, dict) and Path(str(asset.get("source", ""))).name == path.name:
                role = asset.get("role")
                if isinstance(role, str) and role.strip():
                    return role.strip()
    return kind


def prepare_reference_analysis(
    attachments: Iterable[Path],
    visual_analysis: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[Path]]:
    """Merge real media attachments with structured vision output.

    visual_analysis must come from the Codex visual capability (or an injected
    test double). This function only validates and normalizes the handoff; it
    never fabricates semantic observations.
    """

    paths = [Path(item).resolve() for item in attachments]
    if not paths:
        return copy.deepcopy(visual_analysis or {}), []
    if not isinstance(visual_analysis, dict) or not visual_analysis:
        raise OrchestrationError(
            "Las referencias adjuntas requieren análisis visual del orquestador; "
            "el script Python no simula visión."
        )
    for path in paths:
        if not path.is_file():
            raise OrchestrationError("No existe la referencia adjunta: %s" % path)

    analysis = copy.deepcopy(visual_analysis)
    existing_assets = analysis.get("assets", [])
    if not isinstance(existing_assets, list):
        existing_assets = []
    assets_by_name = {
        Path(str(item.get("source", ""))).name: item
        for item in existing_assets
        if isinstance(item, dict) and item.get("source")
    }
    normalized_assets: List[Dict[str, Any]] = []
    used_ids = set()
    for index, path in enumerate(paths):
        kind = _media_kind(path)
        existing = assets_by_name.get(path.name, {})
        role = _role_for(path, kind, analysis)
        asset_id = _safe_id(str(existing.get("id", role)), "asset_%02d" % (index + 1))
        base_id = asset_id
        counter = 2
        while asset_id in used_ids:
            asset_id = "%s_%02d" % (base_id, counter)
            counter += 1
        used_ids.add(asset_id)
        normalized_assets.append({
            "id": asset_id,
            "role": role,
            "source": path.name,
            "preserve_or_reconstruct": str(existing.get("preserve_or_reconstruct", "preserve")),
            "required": bool(existing.get("required", True)),
            **({"media_type": existing["media_type"]} if "media_type" in existing else {}),
            **({"expected": copy.deepcopy(existing["expected"])} if "expected" in existing else {}),
        })
    analysis["assets"] = normalized_assets
    analysis["reference_count"] = len(paths)
    analysis["analysis_provenance"] = {
        "status": "structured",
        "provider": "codex_vision",
        "attachment_count": len(paths),
        "orchestration_version": ORCHESTRATION_VERSION,
    }
    return analysis, paths


def stage_attachments(attachments: Iterable[Path], input_dir: Path) -> List[Path]:
    """Copy supplied references into the visible AE Graphic Lab input folder."""

    input_dir.mkdir(parents=True, exist_ok=True)
    staged: List[Path] = []
    for source in attachments:
        source_path = Path(source).resolve()
        destination = input_dir / source_path.name
        if source_path != destination.resolve():
            shutil.copy2(source_path, destination)
        staged.append(destination)
    return staged


def analysis_from_capability(
    attachments: Iterable[Path],
    analyzer: Callable[[List[str]], Dict[str, Any]],
) -> Dict[str, Any]:
    """Invoke an injected visual capability without coupling the core to Codex APIs."""

    paths = [str(Path(item).resolve()) for item in attachments]
    result = analyzer(paths)
    if not isinstance(result, dict) or not result:
        raise OrchestrationError("La capacidad visual no devolvió un análisis estructurado.")
    return result


def parse_orchestration_envelope(payload: Any) -> Dict[str, Any]:
    """Validate the internal stdin envelope used by graphic-spec-builder."""

    if not isinstance(payload, dict):
        raise OrchestrationError("El envelope del orquestador debe ser un objeto JSON.")
    if payload.get("version") != ORCHESTRATION_VERSION:
        raise OrchestrationError("Versión de envelope no soportada.")
    request = payload.get("request")
    if not isinstance(request, str) or not request.strip():
        raise OrchestrationError("El envelope no contiene request.")
    attachments = payload.get("attachments", [])
    if not isinstance(attachments, list) or not all(isinstance(item, str) and item for item in attachments):
        raise OrchestrationError("attachments debe ser una lista de rutas entregadas por el orquestador.")
    visual_analysis = payload.get("visual_analysis")
    myfonts_response = payload.get("myfonts_response")
    if myfonts_response is not None and not isinstance(myfonts_response, dict):
        raise OrchestrationError("myfonts_response debe ser un objeto o null.")
    return {
        "request": request,
        "attachments": [Path(item) for item in attachments],
        "visual_analysis": visual_analysis,
        "myfonts_response": myfonts_response,
    }
