"""Portable media contract. No filesystem probing or codec/transcode promises."""

from __future__ import annotations

import ntpath
from typing import Any


# Deliberately conservative AE 24.x native-import subset, not all visual references.
MEDIA_EXTENSIONS = {
    "image": [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".psd", ".ai", ".eps", ".pdf", ".exr"],
    "video": [".avi", ".mp4", ".mov", ".m4v", ".mxf"],
    "audio": [".wav", ".aif", ".aiff", ".mp3"],
}
ROLE_TYPES = {
    "background_image": "image", "card_content": "image", "article_capture": "image",
    "image": "image", "logo": "image", "icon": "image",
    "background_video": "video", "video": "video",
    "audio": "audio", "music": "audio", "voiceover": "audio",
}


def media_kind(asset: dict[str, Any]) -> str | None:
    if asset.get("media_type"):
        return asset["media_type"]
    if asset.get("role") in ROLE_TYPES:
        return ROLE_TYPES[asset["role"]]
    extension = ntpath.splitext(str(asset.get("source", "")))[1].lower()
    return next((kind for kind, extensions in MEDIA_EXTENSIONS.items() if extension in extensions), None)


def media_requirements(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Compile only assets actually used as footage; visual-only references stay out."""
    result = []
    for asset in spec["assets"]:
        users = [item for item in spec["elements"]
                 if item.get("asset_id", item.get("appearance", {}).get("asset_id")) == asset["id"]]
        if not users:
            continue
        item = dict(asset)
        item["media_type"] = media_kind(asset)
        item["expected_filename"] = ntpath.basename(asset["source"])
        item["require_audio"] = item["media_type"] == "audio" or any(
            "audio_gain_percent" in user.get("appearance", {}) or any(
                anim["element"] == user["id"] and anim["property"] == "audio_gain_percent"
                for anim in spec["animation"]
            ) for user in users
        )
        # Existing renderer plays footage from zero for the full composition.
        item["minimum_duration"] = spec["composition"]["duration_seconds"] if item["media_type"] != "image" else 0
        result.append(item)
    return result


def validate_media(spec: dict[str, Any]) -> list[str]:
    errors = []
    for asset in media_requirements(spec):
        name = asset["source"]
        kind = asset["media_type"]
        role = asset["role"]
        prefix = "Asset %s (rol %s; esperado %s): " % (asset["id"], role, asset["expected_filename"])
        if ntpath.isabs(name) or ".." in name.replace("\\", "/").split("/"):
            errors.append(prefix + "source debe ser una ruta relativa sin '..'.")
        if kind not in MEDIA_EXTENSIONS or ntpath.splitext(name)[1].lower() not in MEDIA_EXTENSIONS.get(kind, []):
            errors.append(prefix + "formato no compatible con AE 24.x para %s; entrega un medio admitido. No hay transcodificación automática." % kind)
        if role in ROLE_TYPES and ROLE_TYPES[role] != kind:
            errors.append(prefix + "media_type contradice el rol.")
        if not asset.get("required"):
            errors.append(prefix + "un asset utilizado por una capa debe ser required=true.")
        for element in spec["elements"]:
            if element.get("asset_id", element.get("appearance", {}).get("asset_id")) != asset["id"]:
                continue
            element_kind = "image" if element["type"] in ("raster", "icon") else element["type"]
            if element_kind != kind:
                errors.append(prefix + "tipo de elemento %s incompatible con %s." % (element["type"], kind))
        expected = asset.get("expected", {})
        if kind in ("image", "video") and expected.get("has_video") is False:
            errors.append(prefix + "el medio visual requiere has_video=true.")
        if asset["require_audio"] and expected.get("has_audio") is False:
            errors.append(prefix + "el fundido/medio requiere has_audio=true.")
    return errors
