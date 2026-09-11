"""Natural-language input gate and deterministic GRAPHIC_SPEC builder."""

from __future__ import annotations

import ntpath
import copy
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from .myfonts_adapter import normalize_myfonts_response
from .schema_validation import validate_graphic_spec_schema
from .media_contract import validate_media


DEFAULT_FPS = 30.0
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DURATION_QUESTION = "¿Qué duración exacta debe tener el gráfico?"


class DurationRequiredError(ValueError):
    """Raised before a final GRAPHIC_SPEC exists."""

    def __init__(self) -> None:
        super().__init__(DURATION_QUESTION)
        self.question = DURATION_QUESTION


def _plain(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _number(value: str) -> float:
    return float(value.replace(",", "."))


def parse_timing_and_format(request_text: str) -> Dict[str, Any]:
    plain = _plain(request_text)
    fps_match = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*fps\b", plain)
    fps = _number(fps_match.group(1)) if fps_match else DEFAULT_FPS
    if fps <= 0 or fps > 240:
        raise ValueError("FPS debe estar entre 0 y 240.")

    resolution = re.search(r"(?<!\d)(\d{2,5})\s*[x×]\s*(\d{2,5})(?!\d)", request_text, re.IGNORECASE)
    width = int(resolution.group(1)) if resolution else DEFAULT_WIDTH
    height = int(resolution.group(2)) if resolution else DEFAULT_HEIGHT

    frames_match = re.search(r"(?<!\d)(\d+)\s*(?:frames?|fotogramas?)\b", plain)
    seconds_match = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:s\b|segundos?\b|secs?\b|seconds?\b)", plain)
    # A secondary phrase such as "fundido en los últimos 15 fotogramas" must
    # not replace an explicit composition duration given in seconds.
    if frames_match and not seconds_match:
        frame_count = int(frames_match.group(1))
        duration_seconds = frame_count / fps
        duration_source = "frames"
    elif seconds_match:
        duration_seconds = _number(seconds_match.group(1))
        frame_count = int(round(duration_seconds * fps))
        duration_source = "seconds"
    else:
        raise DurationRequiredError()

    if duration_seconds <= 0 or frame_count < 1:
        raise ValueError("La duración debe ser mayor que cero.")
    if width < 16 or height < 16:
        raise ValueError("La resolución debe ser de al menos 16x16.")

    return {
        "duration_seconds": round(duration_seconds, 9),
        "frame_count": frame_count,
        "fps": fps,
        "width": width,
        "height": height,
        "duration_source": duration_source,
        "fps_explicit": fps_match is not None,
        "resolution_explicit": resolution is not None,
    }


def _constraint(path: str, value: Any, request_text: str) -> Dict[str, Any]:
    return {"path": path, "value": value, "source_text": request_text.strip()}


def extract_constraints(request_text: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    plain = _plain(request_text)
    constraints: List[Dict[str, Any]] = []
    resolved: Dict[str, Any] = {}

    if re.search(r"(?:entrada|entrad[ae]|entra)\s+(?:desde\s+)?abajo|desde abajo", plain):
        resolved["entry_direction"] = "bottom"
        constraints.append(_constraint("animation.entry.direction", "bottom", request_text))
    if re.search(r"sin\s+(?:rebote|overshoot)", plain):
        resolved["overshoot"] = False
        constraints.append(_constraint("animation.entry.overshoot", False, request_text))
    if re.search(r"(?:salida|sale|sacala|sacalo).*?(?:derecha)|hacia la derecha", plain):
        resolved["exit_direction"] = "right"
        constraints.append(_constraint("animation.exit.direction", "right", request_text))
    if re.search(r"(?:tarjeta|card).*?(?:centrad[ao]|central)|(?:centrad[ao]|central).*?(?:tarjeta|card)", plain):
        resolved["card_position"] = "center"
        constraints.append(_constraint("layout.card.position", "center", request_text))
    if re.search(r"desenfoc|blur", plain):
        resolved["background_blur"] = True
        constraints.append(_constraint("background.blur", True, request_text))

    count_match = re.search(r"\b(uno|una|un|dos|tres|cuatro|\d+)\s+(?:subrayados?|highlights?)", plain)
    if count_match:
        words = {"uno": 1, "una": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4}
        count = words.get(count_match.group(1), int(count_match.group(1)) if count_match.group(1).isdigit() else 1)
        resolved["highlight_count"] = count
        constraints.append(_constraint("highlight.count", count, request_text))

    colors = {
        "azul": "#1769FF",
        "blue": "#1769FF",
        "amarillo": "#FFD43B",
        "yellow": "#FFD43B",
        "rojo": "#FF3B30",
        "red": "#FF3B30",
        "verde": "#27AE60",
        "green": "#27AE60",
    }
    if re.search(r"subrayad|highlight", plain):
        for word, color in colors.items():
            if re.search(r"\b" + re.escape(word) + r"(?:es)?\b", plain):
                resolved["highlight_color"] = color
                constraints.append(_constraint("highlight.color", color, request_text))
                break

    return constraints, resolved


def _position(value: Any, width: int, height: int) -> List[float]:
    named = {
        "center": [width / 2.0, height / 2.0],
        "upper_left": [width * 0.32, height * 0.34],
        "upper_right": [width * 0.68, height * 0.34],
        "lower_left": [width * 0.32, height * 0.66],
        "lower_right": [width * 0.68, height * 0.66],
    }
    if isinstance(value, list) and len(value) == 2:
        x = float(value[0]) * width if abs(float(value[0])) <= 1 else float(value[0])
        y = float(value[1]) * height if abs(float(value[1])) <= 1 else float(value[1])
        return [round(x, 3), round(y, 3)]
    return [round(v, 3) for v in named.get(str(value), named["center"])]


def _hex(value: Any, fallback: str) -> str:
    if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value.strip()):
        return value.strip().upper()
    return fallback


def _normalize_assets(reference: Dict[str, Any]) -> List[Dict[str, Any]]:
    assets: List[Dict[str, Any]] = []
    raw_assets = reference.get("assets", [])
    if not isinstance(raw_assets, list):
        return assets
    for index, asset in enumerate(raw_assets):
        if not isinstance(asset, dict) or not asset.get("source"):
            continue
        raw_source = str(asset["source"])
        safe_source = ntpath.basename(raw_source) if re.match(r"^(?:[A-Za-z]:[\\/]|/)", raw_source) else raw_source
        assets.append({
            "id": str(asset.get("id", "asset_%02d" % (index + 1))),
            "role": str(asset.get("role", "reference")),
            "source": safe_source,
            "preserve_or_reconstruct": str(
                asset.get("preserve_or_reconstruct", "reconstruct" if asset.get("editable") else "preserve")
            ),
            "required": bool(asset.get("required", True)),
            **({"media_type": asset["media_type"]} if "media_type" in asset else {}),
            **({"expected": copy.deepcopy(asset["expected"])} if "expected" in asset else {}),
        })
    return assets


def _asset_for_role(assets: List[Dict[str, Any]], roles: Tuple[str, ...]) -> Optional[Dict[str, Any]]:
    for role in roles:
        for asset in assets:
            if asset.get("role") == role:
                return asset
    return None


def _choose_preset(request_text: str, reference: Dict[str, Any]) -> Tuple[str, str]:
    requested = reference.get("preset")
    if isinstance(requested, dict):
        requested = requested.get("id")
    if requested in ("editorial_card", "title_panel", "custom"):
        return str(requested), "reference"
    if isinstance(reference.get("elements"), list) and reference["elements"]:
        return "custom", "reference"
    plain = _plain(request_text)
    editorial_terms = (
        "articulo", "captura", "editorial", "tarjeta", "card", "subrayad", "highlight",
    )
    editorial_evidence = any(term in plain for term in editorial_terms)
    editorial_evidence = editorial_evidence or any(
        key in reference for key in ("highlight_count", "background_blur", "video_metadata")
    )
    layout = reference.get("layout")
    editorial_evidence = editorial_evidence or (
        isinstance(layout, dict) and any(str(key).startswith("card_") for key in layout)
    )
    return ("editorial_card", "inferred") if editorial_evidence else ("title_panel", "inferred")


def _timing_windows(frame_count: int, video_metadata: Dict[str, Any]) -> Tuple[int, int]:
    entry_frames = min(max(1, int(round(frame_count * 0.14))), max(1, frame_count - 1))
    exit_frames = min(max(1, int(round(frame_count * 0.13))), max(1, frame_count - 1))
    exit_start = max(entry_frames, frame_count - 1 - exit_frames)
    if video_metadata.get("events") and int(video_metadata.get("frame_count", 0)) > 1:
        events = {
            str(item.get("name")): int(item.get("frame", 0))
            for item in video_metadata["events"]
            if isinstance(item, dict) and item.get("name") is not None
        }
        reference_last = int(video_metadata["frame_count"]) - 1
        if "entry_end" in events:
            entry_frames = max(
                1,
                min(frame_count - 1, int(round(events["entry_end"] / reference_last * (frame_count - 1)))),
            )
        if "exit_start" in events:
            exit_start = max(
                entry_frames,
                min(frame_count - 1, int(round(events["exit_start"] / reference_last * (frame_count - 1)))),
            )
    return entry_frames, exit_start


def _motion_offset(direction: Any, width: int, height: int, amount: float) -> List[float]:
    return {
        "bottom": [0, round(height * amount, 3)],
        "top": [0, -round(height * amount, 3)],
        "left": [-round(width * amount, 3), 0],
        "right": [round(width * amount, 3), 0],
    }.get(str(direction), [0, round(height * amount, 3)])


def _position_animations(
    elements: List[Dict[str, Any]],
    frame_count: int,
    entry_frames: int,
    exit_start: int,
    entry_direction: Any,
    exit_direction: Any,
    width: int,
    height: int,
    overshoot: bool,
) -> List[Dict[str, Any]]:
    animation: List[Dict[str, Any]] = []
    entry_offset = _motion_offset(entry_direction, width, height, 0.18)
    exit_offset = _motion_offset(exit_direction, width, height, 0.18)
    for element in elements:
        if element["id"] in ("bg", "bg_media", "blur") or "position" not in element.get("geometry", {}):
            continue
        base = element["geometry"]["position"]
        animation.append({
            "element": element["id"],
            "property": "position",
            "start_frame": 0,
            "end_frame": entry_frames,
            "start_value": [base[0] + entry_offset[0], base[1] + entry_offset[1]],
            "end_value": base,
            "interpolation": "bezier",
            "easing": {
                "type": "ease_out",
                "influence": 70,
                "overshoot": bool(overshoot),
                **({"overshoot_amount": 0.08} if overshoot else {}),
            },
            "motion_blur": True,
        })
        animation.append({
            "element": element["id"],
            "property": "position",
            "start_frame": exit_start,
            "end_frame": frame_count - 1,
            "start_value": base,
            "end_value": [base[0] + exit_offset[0], base[1] + exit_offset[1]],
            "interpolation": "bezier",
            "easing": {"type": "ease_in", "influence": 70, "overshoot": False},
            "motion_blur": True,
        })
    return animation


def _typography_entries(
    elements: List[Dict[str, Any]],
    typography_ref: Any,
    font_result: Dict[str, Any],
    height: int,
) -> List[Dict[str, Any]]:
    text_ids = [item["id"] for item in elements if item.get("type") == "text"]
    if isinstance(typography_ref, list):
        result: List[Dict[str, Any]] = []
        by_element = {item.get("element"): item for item in typography_ref if isinstance(item, dict)}
        for element_id in text_ids:
            item = by_element.get(element_id, {})
            provider = str(item.get("provider", "fallback"))
            font = item.get("font") if provider == "explicit" else font_result.get("font")
            confidence = str(item.get("confidence", font_result.get("confidence", "unresolved")))
            if not font:
                confidence = "unresolved"
                provider = "fallback"
            result.append({
                "element": element_id,
                "font": font,
                "confidence": confidence,
                "fallback": str(item.get("fallback", "ArialMT")),
                "size": float(item.get("size", max(28, round(height * 0.06)))),
                "leading": float(item.get("leading", max(34, round(height * 0.072)))),
                "tracking": float(item.get("tracking", -10)),
                "alignment": str(item.get("alignment", "center")),
                "provider": "myfonts" if font_result.get("font") else provider,
            })
        return result

    settings = typography_ref if isinstance(typography_ref, dict) else {}
    return [{
        "element": element_id,
        "font": font_result.get("font"),
        "confidence": font_result.get("confidence", "unresolved"),
        "fallback": str(settings.get("fallback", "ArialMT")),
        "size": float(settings.get("size", max(28, round(height * 0.06)))),
        "leading": float(settings.get("leading", max(34, round(height * 0.072)))),
        "tracking": float(settings.get("tracking", -10)),
        "alignment": str(settings.get("alignment", "center")),
        "provider": "myfonts" if font_result.get("font") else "fallback",
    } for element_id in text_ids]


def _editorial_architecture(
    reference: Dict[str, Any],
    assets: List[Dict[str, Any]],
    explicit: Dict[str, Any],
    timing: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], str]:
    width = timing["width"]
    height = timing["height"]
    frame_count = timing["frame_count"]
    layout = reference.get("layout", {}) if isinstance(reference.get("layout", {}), dict) else {}
    colors = reference.get("colors", {}) if isinstance(reference.get("colors", {}), dict) else {}
    motion = reference.get("motion", {}) if isinstance(reference.get("motion", {}), dict) else {}
    video_metadata = reference.get("video_metadata", {}) if isinstance(reference.get("video_metadata", {}), dict) else {}
    card_position_name = explicit.get("card_position", layout.get("card_position", "center"))
    card_position = _position(card_position_name, width, height)
    card_width = int(layout.get("card_width", round(width * 0.58)))
    card_height = int(layout.get("card_height", round(height * 0.54)))
    card_radius = float(layout.get("corner_radius", round(min(width, height) * 0.022)))
    entry_direction = explicit.get("entry_direction", motion.get("entry_direction", "bottom"))
    exit_direction = explicit.get("exit_direction", motion.get("exit_direction", "right"))
    overshoot = explicit.get("overshoot", bool(motion.get("overshoot", False)))
    highlight_count = max(0, min(int(explicit.get("highlight_count", reference.get("highlight_count", 0))), 8))
    highlight_color = explicit.get("highlight_color", _hex(colors.get("highlight"), "#1769FF"))
    background_blur = explicit.get("background_blur", bool(reference.get("background_blur", False)))
    background_asset = _asset_for_role(assets, ("background_video", "background_image"))
    content_asset = _asset_for_role(assets, ("card_content", "article_capture", "image"))

    elements: List[Dict[str, Any]] = []
    order = 1
    if background_asset:
        elements.append({
            "id": "bg_media",
            "label": "BG_VIDEO" if background_asset["role"] == "background_video" else "BG_IMAGE",
            "type": "video" if background_asset["role"] == "background_video" else "image",
            "asset_id": background_asset["id"],
            "geometry": {"position": [width / 2.0, height / 2.0], "size": [width, height]},
            "appearance": {"opacity": 100, "fit": "cover"},
            "layer_order": order,
        })
    else:
        elements.append({
            "id": "bg",
            "label": "BG",
            "type": "solid",
            "geometry": {"position": [width / 2.0, height / 2.0], "size": [width, height]},
            "appearance": {"color": _hex(colors.get("background"), "#15171C"), "opacity": 100},
            "layer_order": order,
        })
    order += 1
    if background_blur:
        elements.append({
            "id": "blur",
            "label": "BLUR",
            "type": "adjustment",
            "geometry": {"position": [width / 2.0, height / 2.0], "size": [width, height]},
            "appearance": {"blurriness": float(reference.get("blur_amount", 24)), "opacity": 100},
            "layer_order": order,
        })
        order += 1
    elements.extend([
        {
            "id": "card_shadow",
            "label": "CARD_SHADOW",
            "type": "shadow",
            "geometry": {
                "position": [card_position[0] + 10, card_position[1] + 18],
                "size": [card_width, card_height],
                "roundness": card_radius,
            },
            "appearance": {"color": "#000000", "opacity": 24},
            "layer_order": order,
        },
        {
            "id": "card",
            "label": "CARD",
            "type": "panel",
            "geometry": {"position": card_position, "size": [card_width, card_height], "roundness": card_radius},
            "appearance": {"color": _hex(colors.get("card"), "#F7F4EE"), "opacity": 100},
            "layer_order": order + 1,
        },
    ])
    order += 2
    if content_asset:
        content_size = [card_width - 80, card_height - 80]
        elements.extend([
            {
                "id": "card_content",
                "label": "CARD_CONTENT",
                "type": "image" if content_asset["role"] != "background_video" else "video",
                "asset_id": content_asset["id"],
                "matte_id": "card_matte",
                "geometry": {"position": card_position, "size": content_size, "roundness": card_radius},
                "appearance": {"opacity": 100, "fit": "cover"},
                "layer_order": order,
            },
            {
                "id": "card_matte",
                "label": "CARD_MATTE",
                "type": "matte",
                "geometry": {"position": card_position, "size": content_size, "roundness": card_radius},
                "appearance": {"color": "#FFFFFF", "opacity": 100},
                "layer_order": order + 1,
            },
        ])
        order += 2
    highlight_ids: List[str] = []
    for index in range(highlight_count):
        element_id = "hl_%02d" % (index + 1)
        size = [round(card_width * 0.42, 3), 12]
        highlight_ids.append(element_id)
        elements.append({
            "id": element_id,
            "label": "HL_%02d" % (index + 1),
            "type": "shape",
            "geometry": {
                "position": [card_position[0], round(card_position[1] + card_height * (0.08 + index * 0.075), 3)],
                "size": size,
                "roundness": 6,
            },
            "appearance": {"color": highlight_color, "opacity": 100},
            "layer_order": order,
        })
        order += 1
    text_data = reference.get("text", {}) if isinstance(reference.get("text", {}), dict) else {}
    title_box = [card_width * 0.8, card_height * 0.22]
    elements.append({
        "id": "title",
        "label": "TITLE",
        "type": "text",
        "text_mode": "paragraph",
        "text_box": {"width": title_box[0], "height": title_box[1]},
        "anchor_strategy": "source_rect_center",
        "geometry": {
            "position": [card_position[0], card_position[1] - card_height * 0.23],
            "size": title_box,
        },
        "appearance": {
            "color": _hex(colors.get("text"), "#15171C"),
            "opacity": 100,
            "text": str(text_data.get("title", "Título")),
        },
        "layer_order": order,
    })

    entry_frames, exit_start = _timing_windows(frame_count, video_metadata)
    animation = _position_animations(
        elements, frame_count, entry_frames, exit_start, entry_direction, exit_direction,
        width, height, bool(overshoot),
    ) if frame_count >= 2 else []
    for index, element_id in enumerate(highlight_ids):
        element = next(item for item in elements if item["id"] == element_id)
        start = min(exit_start, entry_frames + index * max(1, int(round(frame_count * 0.02))))
        end = min(exit_start, start + max(1, int(round(frame_count * 0.08))))
        if end > start:
            animation.append({
                "element": element_id,
                "property": "shape_size",
                "origin": "left",
                "start_frame": start,
                "end_frame": end,
                "start_value": [0, element["geometry"]["size"][1]],
                "end_value": element["geometry"]["size"],
                "interpolation": "bezier",
                "easing": {"type": "ease_out", "influence": 70, "overshoot": False},
                "motion_blur": False,
            })
    if background_blur and frame_count >= 2:
        animation.append({
            "element": "blur",
            "property": "blur",
            "start_frame": 0,
            "end_frame": entry_frames,
            "start_value": 0,
            "end_value": float(reference.get("blur_amount", 24)),
            "interpolation": "bezier",
            "easing": {"type": "ease_out", "influence": 65, "overshoot": False},
            "motion_blur": False,
        })
    controls = [{
        "id": "title_text",
        "label": "Título",
        "property": "source_text",
        "targets": ["title"],
        "purpose": "Texto principal editable",
    }]
    if highlight_ids:
        controls.append({
            "id": "highlight_color",
            "label": "Color de subrayado",
            "property": "fill_color",
            "targets": highlight_ids,
            "master": True,
            "purpose": "Color maestro para todos los subrayados",
        })
    return elements, animation, controls, "%s entry, %s exit" % (entry_direction, exit_direction)


def _title_panel_architecture(
    reference: Dict[str, Any],
    assets: List[Dict[str, Any]],
    timing: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], str]:
    width = timing["width"]
    height = timing["height"]
    frame_count = timing["frame_count"]
    colors = reference.get("colors", {}) if isinstance(reference.get("colors", {}), dict) else {}
    text_data = reference.get("text", {}) if isinstance(reference.get("text", {}), dict) else {}
    background_asset = _asset_for_role(assets, ("background_video", "background_image"))
    icon_asset = _asset_for_role(assets, ("icon", "logo"))
    elements: List[Dict[str, Any]] = []
    if background_asset:
        elements.append({
            "id": "bg_media",
            "label": "BG_VIDEO" if background_asset["role"] == "background_video" else "BG_IMAGE",
            "type": "video" if background_asset["role"] == "background_video" else "image",
            "asset_id": background_asset["id"],
            "geometry": {"position": [width / 2.0, height / 2.0], "size": [width, height]},
            "appearance": {"opacity": 100, "fit": "cover"},
            "layer_order": 1,
        })
    else:
        elements.append({
            "id": "bg",
            "label": "BG",
            "type": "solid",
            "geometry": {"position": [width / 2.0, height / 2.0], "size": [width, height]},
            "appearance": {"color": _hex(colors.get("background"), "#0F172A"), "opacity": 100},
            "layer_order": 1,
        })
    panel_position = [width * 0.5, height * 0.68]
    panel_size = [width * 0.72, height * 0.24]
    elements.append({
        "id": "panel",
        "label": "PANEL",
        "type": "panel",
        "geometry": {"position": panel_position, "size": panel_size, "roundness": min(width, height) * 0.018},
        "appearance": {"color": _hex(colors.get("panel"), "#172554"), "opacity": 94},
        "layer_order": 2,
    })
    if icon_asset:
        elements.append({
            "id": "icon",
            "label": "ICON",
            "type": "icon",
            "asset_id": icon_asset["id"],
            "geometry": {"position": [width * 0.22, height * 0.68], "size": [height * 0.105, height * 0.105]},
            "appearance": {"opacity": 100, "fit": "contain"},
            "layer_order": 3,
        })
    else:
        elements.append({
            "id": "icon",
            "label": "ICON",
            "type": "icon",
            "geometry": {
                "position": [width * 0.22, height * 0.68],
                "size": [height * 0.105, height * 0.105],
                "shape": "ellipse",
                "roundness": 0,
            },
            "appearance": {"color": _hex(colors.get("accent"), "#38BDF8"), "opacity": 100},
            "layer_order": 3,
        })
    title_box = [width * 0.5, height * 0.15]
    elements.append({
        "id": "title",
        "label": "TITLE",
        "type": "text",
        "text_mode": "paragraph",
        "text_box": {"width": title_box[0], "height": title_box[1]},
        "anchor_strategy": "source_rect_center",
        "geometry": {"position": [width * 0.57, height * 0.68], "size": title_box},
        "appearance": {
            "color": _hex(colors.get("text"), "#F8FAFC"),
            "opacity": 100,
            "text": str(text_data.get("title", "Título")),
        },
        "layer_order": 4,
    })
    if frame_count < 2:
        animation: List[Dict[str, Any]] = []
    else:
        entry_frames, exit_start = _timing_windows(frame_count, {})
        animation = [
            {
                "element": "panel", "property": "scale", "start_frame": 0, "end_frame": entry_frames,
                "start_value": [92, 92], "end_value": [100, 100], "interpolation": "bezier",
                "easing": {"type": "ease_out", "influence": 72, "overshoot": False}, "motion_blur": True,
            },
            {
                "element": "icon", "property": "rotation", "start_frame": 0, "end_frame": entry_frames,
                "start_value": -24, "end_value": 0, "interpolation": "bezier",
                "easing": {"type": "ease_out", "influence": 64, "overshoot": True, "overshoot_amount": 0.12},
                "motion_blur": True,
            },
            {
                "element": "title", "property": "opacity", "start_frame": 0, "end_frame": entry_frames,
                "start_value": 0, "end_value": 100, "interpolation": "bezier",
                "easing": {"type": "ease_in_out", "influence": 60, "overshoot": False}, "motion_blur": False,
            },
            {
                "element": "panel", "property": "opacity", "start_frame": exit_start, "end_frame": frame_count - 1,
                "start_value": 94, "end_value": 0, "interpolation": "bezier",
                "easing": {"type": "ease_in", "influence": 68, "overshoot": False}, "motion_blur": False,
            },
            {
                "element": "icon", "property": "opacity", "start_frame": exit_start, "end_frame": frame_count - 1,
                "start_value": 100, "end_value": 0, "interpolation": "bezier",
                "easing": {"type": "ease_in", "influence": 68, "overshoot": False}, "motion_blur": False,
            },
            {
                "element": "title", "property": "opacity", "start_frame": exit_start, "end_frame": frame_count - 1,
                "start_value": 100, "end_value": 0, "interpolation": "bezier",
                "easing": {"type": "ease_in", "influence": 68, "overshoot": False}, "motion_blur": False,
            },
        ]
    controls = [
        {
            "id": "title_text", "label": "Título", "property": "source_text",
            "targets": ["title"], "purpose": "Texto principal editable",
        },
        {
            "id": "panel_color", "label": "Color del panel", "property": "fill_color",
            "targets": ["panel"], "purpose": "Color editable del panel",
        },
    ]
    return elements, animation, controls, "scale, rotation and opacity"


def _custom_architecture(reference: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], str]:
    elements = copy.deepcopy(reference.get("elements", []))
    animation = copy.deepcopy(reference.get("animation", []))
    controls = copy.deepcopy(reference.get("essential_graphics", []))
    if "essential_graphics" not in reference:
        controls = [
            {
                "id": "%s_text" % item["id"],
                "label": item["label"].title().replace("_", " "),
                "property": "source_text",
                "targets": [item["id"]],
                "purpose": "Texto editable",
            }
            for item in elements if item.get("type") == "text"
        ]
    return elements, animation, controls, str(reference.get("inferred_direction", "custom motion"))


def build_graphic_spec(
    request_text: str,
    reference_analysis: Optional[Dict[str, Any]] = None,
    myfonts_response: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(request_text, str) or not request_text.strip():
        raise DurationRequiredError()

    timing = parse_timing_and_format(request_text)
    constraints, explicit = extract_constraints(request_text)
    reference = reference_analysis or {}
    typography_ref = reference.get("typography", {}) if isinstance(reference.get("typography", {}), dict) else {}

    width = timing["width"]
    height = timing["height"]
    frame_count = timing["frame_count"]
    preset_id, preset_source = _choose_preset(request_text, reference)

    assumptions: List[Dict[str, str]] = []
    if not timing["fps_explicit"]:
        assumptions.append({"decision": "fps=30", "reason": "Default obligatorio del producto", "confidence": "high"})
    if not timing["resolution_explicit"]:
        assumptions.append({"decision": "resolution=1920x1080", "reason": "Default obligatorio del producto", "confidence": "high"})
    layout = reference.get("layout", {}) if isinstance(reference.get("layout", {}), dict) else {}
    motion = reference.get("motion", {}) if isinstance(reference.get("motion", {}), dict) else {}
    if preset_id == "editorial_card" and "card_position" not in explicit:
        card_position_name = layout.get("card_position", "center")
        assumptions.append({
            "decision": "card_position=" + str(card_position_name),
            "reason": "Referencia visual" if "card_position" in layout else "Composición editorial conservadora",
            "confidence": "high" if "card_position" in layout else "medium",
        })
    if preset_id == "editorial_card" and "entry_direction" not in explicit:
        entry_direction = motion.get("entry_direction", "bottom")
        assumptions.append({
            "decision": "entry_direction=" + str(entry_direction),
            "reason": "Movimiento medido en referencia" if "entry_direction" in motion else "Resolución automática",
            "confidence": "high" if "entry_direction" in motion else "medium",
        })
    vague = any(term in _plain(request_text) for term in ("editorial", "elegante", "limpio", "clean", "minimal"))
    if vague:
        assumptions.append({"decision": "easing=bezier suave; sombra y radios moderados", "reason": "La dirección estética era vaga y no bloqueante", "confidence": "medium"})
    video_metadata = reference.get("video_metadata", {}) if isinstance(reference.get("video_metadata", {}), dict) else {}
    if video_metadata.get("events"):
        assumptions.append({"decision": "timing_normalized_to_target_duration", "reason": "Relaciones temporales medidas en la referencia de video", "confidence": "high"})
    assets = _normalize_assets(reference)

    needs_identification = bool(typography_ref.get("requires_identification", False))
    font_result = normalize_myfonts_response(myfonts_response) if needs_identification else {
        "font": None,
        "confidence": "unresolved",
        "candidate_count": 0,
    }
    if needs_identification and font_result["font"] is None:
        assumptions.append({"decision": "font=unresolved; fallback=ArialMT", "reason": "MyFonts no devolvió una identificación utilizable", "confidence": "low"})

    if preset_id == "editorial_card":
        elements, animation, controls, inferred_direction = _editorial_architecture(reference, assets, explicit, timing)
    elif preset_id == "custom":
        elements, animation, controls, inferred_direction = _custom_architecture(reference)
    else:
        elements, animation, controls, inferred_direction = _title_panel_architecture(reference, assets, timing)
    typography_source: Any = reference.get("typography", {})
    typography = _typography_entries(elements, typography_source, font_result, height)
    myfonts_status = font_result["confidence"] if needs_identification else "not_required"
    spec: Dict[str, Any] = {
        "schema_version": "1.1.0",
        "exports": copy.deepcopy(reference.get("exports", {"mogrt": True})),
        "composition": {
            "duration_seconds": timing["duration_seconds"],
            "frame_count": frame_count,
            "fps": timing["fps"],
            "width": width,
            "height": height,
        },
        "targets": {"after_effects": "24.x", "premiere_pro": "2024"},
        "intent": {
            "purpose": request_text.strip(),
            "explicit_constraints": constraints,
            "inferred_direction": inferred_direction,
        },
        "preset": {"id": preset_id, "source": preset_source},
        "assets": assets,
        "elements": elements,
        "typography": typography,
        "animation": animation,
        "essential_graphics": controls,
        "assumptions": assumptions,
        "provenance": {
            "request_text": request_text.strip(),
            "reference_count": int(reference.get("reference_count", 1 if reference else 0)),
            "myfonts": {"status": myfonts_status, "candidate_count": int(font_result["candidate_count"])},
            "reference_analysis": reference.get("analysis_provenance", {
                "status": "not_required",
                "provider": "none",
                "attachment_count": 0,
                "orchestration_version": "1.0",
            }),
        },
    }
    errors = validate_graphic_spec_schema(spec) + validate_graphic_spec(spec)
    if errors:
        raise ValueError("GRAPHIC_SPEC inválido: " + "; ".join(errors))
    return spec


def validate_graphic_spec(spec: Any) -> List[str]:
    # Schema validation is also the public semantic entrypoint's type guard.
    schema_errors = validate_graphic_spec_schema(spec)
    if schema_errors:
        return schema_errors
    errors: List[str] = []
    required = (
        "schema_version", "composition", "targets", "intent", "assets", "elements",
        "typography", "animation", "essential_graphics", "assumptions", "provenance",
    )
    if not isinstance(spec, dict):
        return ["La raíz debe ser un objeto."]
    for key in required:
        if key not in spec:
            errors.append("Falta el campo raíz %s." % key)
    if errors:
        return errors

    comp = spec.get("composition", {})
    for key in ("duration_seconds", "frame_count", "fps", "width", "height"):
        if key not in comp:
            errors.append("Falta composition.%s." % key)
    try:
        duration = float(comp.get("duration_seconds", 0))
        fps = float(comp.get("fps", 0))
        frame_count = int(comp.get("frame_count", 0))
        if duration <= 0 or fps <= 0 or frame_count < 1:
            errors.append("Duración, FPS y frame_count deben ser positivos.")
        if int(round(duration * fps)) != frame_count:
            errors.append("frame_count no coincide con duration_seconds × fps.")
        if int(comp.get("width", 0)) < 16 or int(comp.get("height", 0)) < 16:
            errors.append("Resolución no válida.")
    except (TypeError, ValueError):
        errors.append("Los valores de composición deben ser numéricos.")
        frame_count = 0

    elements = spec.get("elements", [])
    if not isinstance(elements, list) or not elements:
        errors.append("elements debe contener al menos un elemento.")
        elements = []
    ids = [item.get("id") for item in elements if isinstance(item, dict)]
    labels = [item.get("label") for item in elements if isinstance(item, dict)]
    orders = [item.get("layer_order") for item in elements if isinstance(item, dict)]
    if len(ids) != len(set(ids)):
        errors.append("Los ids de elementos deben ser únicos.")
    if len(labels) != len(set(labels)):
        errors.append("Los nombres de capa deben ser únicos.")
    if len(orders) != len(set(orders)):
        errors.append("layer_order debe ser único.")
    for label in labels:
        if not isinstance(label, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", label):
            errors.append("Nombre de capa no funcional: %r." % label)

    assets = spec.get("assets", [])
    asset_ids = [item.get("id") for item in assets if isinstance(item, dict)]
    if len(asset_ids) != len(set(asset_ids)):
        errors.append("Los ids de assets deben ser únicos.")
    element_by_id = {item.get("id"): item for item in elements if isinstance(item, dict)}
    asset_types = {"image", "video", "raster"}
    shape_types = {"shape", "panel", "matte", "line", "shadow", "icon"}
    for item in elements:
        if not isinstance(item, dict):
            continue
        element_id = item.get("id")
        geometry = item.get("geometry", {})
        size = geometry.get("size") if isinstance(geometry, dict) else None
        if item.get("type") in asset_types.union(shape_types) and (
            not isinstance(size, list) or len(size) != 2 or
            not all(isinstance(value, (int, float)) and value > 0 for value in size)
        ):
            errors.append("El elemento %s requiere geometry.size positivo de dos dimensiones." % element_id)
        asset_id = item.get("asset_id", item.get("appearance", {}).get("asset_id"))
        if item.get("type") in asset_types.union({"audio"}) and not asset_id:
            errors.append("El elemento %s requiere asset_id explícito." % element_id)
        if asset_id and asset_id not in asset_ids:
            errors.append("El elemento %s referencia un asset inexistente: %s." % (element_id, asset_id))
        matte_id = item.get("matte_id")
        if matte_id:
            matte = element_by_id.get(matte_id)
            if not matte or matte.get("type") != "matte":
                errors.append("El elemento %s referencia un matte inválido: %s." % (element_id, matte_id))
        try:
            rounded = float(geometry.get("roundness", 0) or 0)
        except (TypeError, ValueError):
            rounded = 0
            errors.append("El elemento %s tiene roundness no numérico." % element_id)
        if item.get("type") in asset_types and rounded > 0 and not matte_id:
            errors.append("El elemento raster %s requiere matte_id para sus esquinas redondeadas." % element_id)
        parent_id = item.get("parent_id")
        if parent_id and parent_id not in element_by_id:
            errors.append("El elemento %s referencia un parent inexistente: %s." % (element_id, parent_id))
        if item.get("text_mode") == "paragraph":
            box = item.get("text_box")
            if not isinstance(box, dict) or not (box.get("width", 0) > 0 and box.get("height", 0) > 0):
                errors.append("El texto paragraph %s requiere width y height positivos." % element_id)
        if "audio_gain_percent" in item.get("appearance", {}) and item.get("type") not in ("video", "audio"):
            errors.append("audio_gain_percent requiere una capa video/audio: %s." % element_id)

    errors.extend(validate_media(spec))

    for item in spec.get("typography", []):
        if item.get("element") not in ids:
            errors.append("Typography referencia un elemento inexistente: %s." % item.get("element"))
        elif element_by_id[item.get("element")].get("type") != "text":
            errors.append("Typography solo puede referenciar elementos text: %s." % item.get("element"))
        confidence = item.get("confidence")
        if confidence not in ("confirmed", "high", "medium", "low", "unresolved"):
            errors.append("Confianza tipográfica no válida.")
        if confidence == "unresolved" and item.get("font") is not None:
            errors.append("Una fuente unresolved no puede declarar un nombre identificado.")

    for index, anim in enumerate(spec.get("animation", [])):
        if anim.get("element") not in ids:
            errors.append("Animación %d referencia un elemento inexistente." % index)
        start = anim.get("start_frame")
        end = anim.get("end_frame")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
            errors.append("Animación %d tiene un intervalo inválido." % index)
        elif end > (frame_count if anim.get("property") == "audio_gain_percent" else frame_count - 1) or start >= frame_count:
            errors.append("Animación %d excede frame_count - 1." % index)
        if anim.get("property") == "audio_gain_percent":
            if element_by_id.get(anim["element"], {}).get("type") not in ("video", "audio"):
                errors.append("Animación de audio %d requiere un elemento video/audio." % index)
            if end <= start:
                errors.append("El fundido de audio debe tener duración positiva.")
        easing_type = anim.get("easing", {}).get("type")
        if easing_type not in ("linear", "ease_in", "ease_out", "ease_in_out"):
            errors.append("Animación %d declara un easing no soportado." % index)
        if anim.get("property") == "shape_size":
            element = element_by_id.get(anim.get("element"), {})
            if element.get("type") not in shape_types or element.get("asset_id"):
                errors.append("Animación %d usa shape_size en un elemento sin Rectangle Path." % index)
            if anim.get("origin") not in ("center", "left", "right", "top", "bottom"):
                errors.append("Animación %d debe declarar origin para shape_size." % index)

    no_overshoot = any(
        item.get("path") == "animation.entry.overshoot" and item.get("value") is False
        for item in spec.get("intent", {}).get("explicit_constraints", [])
    )
    if no_overshoot and any(anim.get("easing", {}).get("overshoot") for anim in spec.get("animation", [])):
        errors.append("La restricción sin rebote fue alterada.")

    highlight_count = next((
        item.get("value") for item in spec.get("intent", {}).get("explicit_constraints", [])
        if item.get("path") == "highlight.count"
    ), None)
    if isinstance(highlight_count, int) and len([label for label in labels if isinstance(label, str) and label.startswith("HL_")]) != highlight_count:
        errors.append("La cantidad explícita de subrayados no fue conservada.")

    controls = spec.get("essential_graphics", [])
    if spec.get("exports", {}).get("mogrt", True) and not controls:
        errors.append("La exportación MOGRT requiere al menos un controlador significativo.")
    control_labels = [item["label"].strip() for item in controls]
    if len(set(control_labels)) != len(control_labels) or not all(control_labels):
        errors.append("Los controles Essential Graphics requieren nombres únicos y no vacíos.")
    controlled_properties = set()
    for index, control in enumerate(controls):
        source_property = control.get("source_property")
        targets = control.get("targets")
        property_name = control.get("property")
        if source_property:
            parts = source_property.split(".", 1)
            target = next((item["id"] for item in elements if item["label"] == parts[0]), None)
            property_name = {"Source Text": "source_text", "Fill Color": "fill_color"}.get(parts[-1])
            targets = [target] if target else []
        if not isinstance(targets, list) or not targets or not property_name:
            errors.append("Control Essential Graphics %d requiere property y targets." % index)
            continue
        missing = [target for target in targets if target not in element_by_id]
        if missing:
            errors.append("Control Essential Graphics %d referencia targets inexistentes: %s." % (index, ", ".join(missing)))
        if len(targets) > 1 and not control.get("master"):
            errors.append("Control Essential Graphics %d compartido requiere master=true." % index)
        if control.get("master") and property_name != "fill_color":
            errors.append("Control Essential Graphics %d solo admite master para fill_color." % index)
        for target in targets:
            element = element_by_id.get(target)
            if not element:
                continue
            kind = element["type"]
            valid = (
                (property_name == "source_text" and kind == "text") or
                (property_name == "fill_color" and kind in shape_types and not element.get("asset_id")) or
                (property_name == "blur" and kind == "adjustment") or
                (property_name in ("opacity", "position", "scale", "rotation") and kind != "audio")
            )
            if not valid:
                errors.append("Control %s no resuelve una propiedad significativa en %s." % (control["label"], target))
            key = (target, property_name)
            if key in controlled_properties:
                errors.append("Propiedad Essential Graphics duplicada: %s.%s." % key)
            controlled_properties.add(key)

    return errors
