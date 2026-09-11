"""Normalize MyFonts/WhatTheFont tool output without inventing font names."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


CONFIDENCE_STATES = {"confirmed", "high", "medium", "low", "unresolved"}


def _confidence_state(value: Any) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in CONFIDENCE_STATES:
            return lowered
        try:
            value = float(lowered.rstrip("%")) / (100.0 if "%" in lowered else 1.0)
        except ValueError:
            return "medium"
    if isinstance(value, (int, float)):
        score = float(value)
        if score > 1:
            score /= 100.0
        if score >= 0.98:
            return "confirmed"
        if score >= 0.85:
            return "high"
        if score >= 0.65:
            return "medium"
        return "low"
    return "medium"


def _candidate_from_dict(item: Dict[str, Any]) -> Optional[Dict[str, str]]:
    name = None
    for key in ("font", "font_name", "fontName", "family", "family_name", "name", "title"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            name = value.strip()
            break
    if not name:
        return None
    confidence = item.get("confidence", item.get("score", item.get("probability")))
    return {"name": name, "confidence": _confidence_state(confidence)}


def _walk_candidate_containers(payload: Any) -> Iterable[Dict[str, str]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                candidate = _candidate_from_dict(item)
                if candidate:
                    yield candidate
                for key in ("candidates", "matches", "results", "fonts", "identified", "structuredContent", "result", "data"):
                    if key in item:
                        yield from _walk_candidate_containers(item[key])
    elif isinstance(payload, dict):
        candidate = _candidate_from_dict(payload)
        if candidate:
            yield candidate
        for key in ("candidates", "matches", "results", "fonts", "identified", "structuredContent", "result", "data"):
            if key in payload:
                yield from _walk_candidate_containers(payload[key])


def normalize_myfonts_response(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return one exact tool-derived selection and normalized metadata.

    Supported integration contract:
    - ``selected_font`` as a string plus optional ``confidence``; or
    - candidate containers named ``candidates``, ``matches``, ``results``,
      ``fonts`` or ``identified``.

    No candidate means ``font`` stays null and status is ``unresolved``.
    """

    if not payload or payload.get("success") is False or payload.get("error"):
        return {"font": None, "confidence": "unresolved", "candidate_count": 0}

    selected = payload.get("selected_font")
    if isinstance(selected, str) and selected.strip():
        candidates: List[Dict[str, str]] = list(_walk_candidate_containers(payload))
        return {
            "font": selected.strip(),
            "confidence": _confidence_state(payload.get("confidence", "high")),
            "candidate_count": max(1, len(candidates)),
        }

    candidates = list(_walk_candidate_containers(payload))
    if not candidates:
        return {"font": None, "confidence": "unresolved", "candidate_count": 0}

    rank = {"confirmed": 4, "high": 3, "medium": 2, "low": 1, "unresolved": 0}
    best = sorted(candidates, key=lambda c: rank[c["confidence"]], reverse=True)[0]
    return {
        "font": best["name"],
        "confidence": best["confidence"],
        "candidate_count": len(candidates),
    }


def build_identification_request(image: str, user_query: str, target_box: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Create the adapter request used by Codex before calling MyFonts."""

    request: Dict[str, Any] = {
        "tool": "mcp__codex_apps__myfonts_detect_font_regions",
        "image": image,
        "user_query": user_query,
    }
    if target_box:
        request["target_box"] = target_box
    return request
