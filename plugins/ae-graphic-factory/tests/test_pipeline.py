from __future__ import annotations

import copy
import json
import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))

from aegf.ae_jsx import generate_jsx  # noqa: E402
from aegf.graphic_spec import (  # noqa: E402
    DURATION_QUESTION,
    DurationRequiredError,
    build_graphic_spec,
    parse_timing_and_format,
    validate_graphic_spec,
)
from aegf.myfonts_adapter import build_identification_request, normalize_myfonts_response  # noqa: E402
from aegf.schema_validation import validate_graphic_spec_schema  # noqa: E402
from aegf.static_validation import validate_jsx  # noqa: E402
from check_dependencies import dependency_report  # noqa: E402
from run_pipeline import run  # noqa: E402


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_uncompressed_avi(path: Path, width: int = 16, height: int = 16, frame_count: int = 3) -> Path:
    """Write a tiny valid RIFF AVI fixture using only the standard library."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return tag + struct.pack("<I", len(data)) + data + (b"\0" if len(data) % 2 else b"")

    def list_chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return b"LIST" + struct.pack("<I", len(payload)) + payload + (b"\0" if len(payload) % 2 else b"")

    row_size = ((width * 3 + 3) // 4) * 4
    frame_size = row_size * height
    frames = []
    for index in range(frame_count):
        color = bytes((40 + index * 40, 30, 100 + index * 30))
        row = color * width + bytes(row_size - width * 3)
        frames.append(row * height)
    avih = struct.pack(
        "<14I", 100000, frame_size * 10, 0, 0, frame_count, 0, 1,
        frame_size, width, height, 0, 0, 0, 0,
    )
    strh = struct.pack(
        "<4s4sIHH8I4h", b"vids", b"DIB ", 0, 0, 0, 0, 1, 10, 0,
        frame_count, frame_size, 0xFFFFFFFF, 0, 0, 0, width, height,
    )
    strf = struct.pack(
        "<IiiHHIIiiII", 40, width, height, 1, 24, 0, frame_size, 0, 0, 0, 0,
    )
    hdrl = list_chunk(b"hdrl", chunk(b"avih", avih) + list_chunk(b"strl", chunk(b"strh", strh) + chunk(b"strf", strf)))
    movi = list_chunk(b"movi", b"".join(chunk(b"00db", frame) for frame in frames))
    payload = b"AVI " + hdrl + movi
    path.write_bytes(b"RIFF" + struct.pack("<I", len(payload)) + payload)
    return path


class InputAndSpecTests(unittest.TestCase):
    def test_01_missing_duration_blocks_before_spec_or_jsx(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder) / "AE_Graphic_Lab"
            result = run("Quiero presentar este artículo.", workspace)
            self.assertEqual(result["GRAPHIC_SPEC_READY"], "FAIL")
            self.assertEqual(result["question"], DURATION_QUESTION)
            self.assertFalse((workspace / "output" / "GRAPHIC_SPEC.json").exists())
            self.assertFalse((workspace / "output" / "crear_grafico.jsx").exists())
        with self.assertRaises(DurationRequiredError):
            build_graphic_spec("Quiero presentar este artículo.")

    def test_02_defaults(self):
        spec = build_graphic_spec("6 segundos. Presenta este artículo.")
        self.assertEqual(spec["composition"], {
            "duration_seconds": 6.0,
            "frame_count": 180,
            "fps": 30.0,
            "width": 1920,
            "height": 1080,
        })

    def test_03_explicit_override(self):
        spec = build_graphic_spec("8 segundos, 60 fps, 1080x1920.")
        comp = spec["composition"]
        self.assertEqual((comp["fps"], comp["width"], comp["height"], comp["frame_count"]), (60.0, 1080, 1920, 480))

    def test_04_concrete_instructions_are_preserved(self):
        spec = build_graphic_spec("6 segundos. Entrada desde abajo sin rebote. Dos subrayados azules y salida a la derecha.")
        constraints = {item["path"]: item["value"] for item in spec["intent"]["explicit_constraints"]}
        self.assertEqual(constraints["animation.entry.direction"], "bottom")
        self.assertIs(constraints["animation.entry.overshoot"], False)
        self.assertEqual(constraints["highlight.count"], 2)
        self.assertEqual(constraints["highlight.color"], "#1769FF")
        self.assertEqual(constraints["animation.exit.direction"], "right")
        highlights = [item for item in spec["elements"] if item["label"].startswith("HL_")]
        self.assertEqual(len(highlights), 2)
        self.assertTrue(all(item["appearance"]["color"] == "#1769FF" for item in highlights))
        self.assertFalse(any(item["easing"]["overshoot"] for item in spec["animation"]))
        card_entry = next(item for item in spec["animation"] if item["element"] == "card" and item["start_frame"] == 0)
        card_exit = next(item for item in spec["animation"] if item["element"] == "card" and item["end_frame"] == 179)
        self.assertGreater(card_entry["start_value"][1], card_entry["end_value"][1])
        self.assertGreater(card_exit["end_value"][0], card_exit["start_value"][0])

    def test_05_vague_idea_is_resolved_without_extra_questions(self):
        spec = build_graphic_spec("6 segundos. Editorial y elegante.")
        decisions = " ".join(item["decision"] for item in spec["assumptions"])
        self.assertIn("easing=bezier", decisions)
        self.assertTrue(all(item["confidence"] in ("high", "medium", "low") for item in spec["assumptions"]))

    def test_06_reference_controls_unspecified_layout_color_and_motion(self):
        reference = fixture("reference_visual.json")
        spec = build_graphic_spec("6 segundos. Preséntalo como la referencia.", reference)
        card = next(item for item in spec["elements"] if item["id"] == "card")
        highlight = next(item for item in spec["elements"] if item["label"] == "HL_01")
        entry = next(item for item in spec["animation"] if item["element"] == "card" and item["start_frame"] == 0)
        self.assertEqual(card["geometry"]["position"], [614.4, 367.2])
        self.assertEqual(highlight["appearance"]["color"], "#FFD43B")
        self.assertLess(entry["start_value"][0], entry["end_value"][0])

    def test_07_myfonts_is_used_and_never_guessed(self):
        reference = fixture("reference_visual.json")
        success = build_graphic_spec("6 segundos. Preséntalo como la referencia.", reference, fixture("myfonts_success.json"))
        type_success = success["typography"][0]
        self.assertEqual(type_success["font"], "Source Serif 4 Semibold")
        self.assertEqual(type_success["provider"], "myfonts")
        failed = build_graphic_spec("6 segundos. Preséntalo como la referencia.", reference, fixture("myfonts_failure.json"))
        type_failed = failed["typography"][0]
        self.assertIsNone(type_failed["font"])
        self.assertEqual(type_failed["confidence"], "unresolved")
        request = build_identification_request("reference-card.png", "identifica el titular")
        self.assertEqual(request["tool"], "mcp__codex_apps__myfonts_detect_font_regions")
        self.assertEqual(normalize_myfonts_response({})["confidence"], "unresolved")

    def test_08_complex_noneditable_content_can_remain_raster(self):
        spec = build_graphic_spec("6 segundos. Presenta la captura.", fixture("reference_visual.json"))
        asset = next(item for item in spec["assets"] if item["id"] == "article_capture")
        raster = next(item for item in spec["elements"] if item["type"] in ("raster", "image"))
        self.assertEqual(asset["preserve_or_reconstruct"], "preserve")
        self.assertEqual(raster.get("asset_id", raster["appearance"].get("asset_id")), "article_capture")

    def test_09_after_effects_names_are_human_readable(self):
        spec = build_graphic_spec("6 segundos. Tarjeta central con dos subrayados azules y fondo desenfocado.")
        labels = [item["label"] for item in spec["elements"]]
        self.assertTrue({"BG", "BLUR", "CARD", "CARD_SHADOW", "HL_01", "HL_02", "TITLE"}.issubset(set(labels)))
        self.assertFalse(any(re.search(r"(?:Layer|Shape Layer|Control)\s+\d+", label, re.I) for label in labels))

    def test_10_no_keyframe_exceeds_frame_budget(self):
        for request in ("6 segundos. Tarjeta editorial.", "8 segundos, 60 fps, 1080x1920. Editorial.", "195 frames. Limpio."):
            spec = build_graphic_spec(request)
            last = spec["composition"]["frame_count"] - 1
            self.assertTrue(all(0 <= item["start_frame"] <= item["end_frame"] <= last for item in spec["animation"]))

    def test_frames_duration_uses_default_fps(self):
        parsed = parse_timing_and_format("195 frames. Tarjeta editorial.")
        self.assertEqual(parsed["frame_count"], 195)
        self.assertEqual(parsed["duration_seconds"], 6.5)
        self.assertEqual(parsed["fps"], 30.0)

    def test_video_timing_is_normalized_to_target_duration(self):
        reference = {"reference_count": 1, "video_metadata": fixture("video_metadata.json")}
        spec = build_graphic_spec("6 segundos. Reproduce el movimiento de la referencia.", reference)
        card_entries = [item for item in spec["animation"] if item["element"] == "card" and item["start_frame"] == 0]
        expected_entry_end = round(16 / 95 * 179)
        self.assertEqual(card_entries[0]["end_frame"], expected_entry_end)
        self.assertIn("timing_normalized_to_target_duration", [item["decision"] for item in spec["assumptions"]])


class JsxAndBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.spec = build_graphic_spec("6 segundos. Fondo desenfocado, tarjeta central, dos subrayados azules y salida a la derecha.")
        self.jsx = generate_jsx(self.spec)

    def test_11_aep_save_precedes_mogrt_export(self):
        self.assertLess(self.jsx.index("app.project.save(aepFile)"), self.jsx.index("exportAsMotionGraphicsTemplate"))

    def test_12_export_return_value_is_checked(self):
        self.assertRegex(self.jsx, r"exportOk\s*=.*exportAsMotionGraphicsTemplate")
        self.assertIn("if (exportOk !== true)", self.jsx)
        self.assertGreater(self.jsx.index("AEP y MOGRT generados correctamente"), self.jsx.index("if (exportOk !== true)"))

    def test_13_jsx_has_no_personal_absolute_paths(self):
        reference = fixture("reference_visual.json")
        separator = chr(92)
        reference["assets"][0]["source"] = "C:" + separator + "Users" + separator + "Someone" + separator + "Private" + separator + "article.png"
        jsx = generate_jsx(build_graphic_spec("6 segundos. Presenta esta captura.", reference))
        self.assertNotRegex(jsx, r"[A-Za-z]:[\\/]+Users[\\/]")
        self.assertIn("article.png", jsx)

    def test_14_premiere_boundary_is_reuse_not_duplication(self):
        integration = (PLUGIN_ROOT / "references" / "premiere-integration.md").read_text(encoding="utf-8")
        self.assertFalse((PLUGIN_ROOT / "skills" / "premiere-jsx-script-creator").exists())
        self.assertIn("reutiliza la skill externa", integration)
        self.assertIn("no incorpora una copia", integration)
        self.assertNotIn("app.project.items.addComp", integration)

    def test_15_premiere_policies_remain_distinct(self):
        fixture_data = fixture("timeline_policies.json")["policies"]
        self.assertEqual(set(fixture_data), {"STRICT_EMPTY", "REUSE", "REPLACE_RANGE"})
        self.assertNotEqual(fixture_data["STRICT_EMPTY"], fixture_data["REUSE"])
        self.assertNotEqual(fixture_data["REUSE"], fixture_data["REPLACE_RANGE"])
        integration = (PLUGIN_ROOT / "references" / "premiere-integration.md").read_text(encoding="utf-8")
        for policy in fixture_data:
            self.assertIn(policy, integration)

    def test_formal_schema_and_semantic_validator(self):
        schema = json.loads((PLUGIN_ROOT / "schemas" / "graphic-spec.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(validate_graphic_spec_schema(fixture("graphic_spec_valid.json")), [])
        self.assertGreater(len(validate_graphic_spec_schema(fixture("graphic_spec_invalid.json"))), 0)
        self.assertEqual(validate_graphic_spec(fixture("graphic_spec_valid.json")), [])
        self.assertGreater(len(validate_graphic_spec(fixture("graphic_spec_invalid.json"))), 0)

    def test_static_validator_accepts_generated_jsx(self):
        result = validate_jsx(self.jsx, strict=True)
        self.assertEqual(result["errors"], [])

    def test_static_validator_rejects_missing_export_check(self):
        broken = self.jsx.replace("if (exportOk !== true)", "if (false)")
        result = validate_jsx(broken)
        self.assertTrue(any("retorno" in error or "éxito" in error for error in result["errors"]))

    def test_end_to_end_without_adobe(self):
        request = "6 segundos. Sobre un fondo de video, presenta una tarjeta central con esquinas redondeadas. Desenfoca el fondo durante la entrada. Añade dos subrayados azules y sácala hacia la derecha."
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder) / "AE_Graphic_Lab"
            result = run(request, workspace)
            self.assertEqual(result["GRAPHIC_SPEC_READY"], "PASS")
            self.assertEqual(result["JSX_GENERATED"], "PASS")
            self.assertEqual(result["STATIC_CHECK_OK"], "PASS")
            self.assertEqual(result["AE_RUNTIME_OK"], "NOT_TESTED")
            self.assertEqual(result["MOGRT_EXPORT_OK"], "NOT_TESTED")
            self.assertEqual(result["PREMIERE_IMPORT_OK"], "NOT_TESTED")
            self.assertEqual(result["PREMIERE_TIMELINE_OK"], "NOT_TESTED")
            self.assertTrue((workspace / "output" / "GRAPHIC_SPEC.json").exists())
            self.assertTrue((workspace / "output" / "crear_grafico.jsx").exists())


class StrengtheningTests(unittest.TestCase):
    def test_attached_image_and_video_use_orchestrator_vision_without_user_json(self):
        analysis = fixture("editorial_visual_analysis.json")
        calls = []

        def visual_capability(paths):
            calls.append(paths)
            return analysis

        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder) / "AE_Graphic_Lab"
            video = make_uncompressed_avi(Path(folder) / "synthetic-video.avi")
            attachments = [video, FIXTURES / "reference-card.png"]
            result = run(
                "6 segundos. Tarjeta editorial con dos subrayados.",
                workspace,
                attachments=attachments,
                visual_analyzer=visual_capability,
            )
            self.assertEqual(result["STATIC_CHECK_OK"], "PASS")
            spec = json.loads((workspace / "output" / "GRAPHIC_SPEC.json").read_text(encoding="utf-8"))
            self.assertEqual(spec["provenance"]["reference_analysis"]["provider"], "codex_vision")
            self.assertEqual(spec["provenance"]["reference_analysis"]["attachment_count"], 2)
            self.assertEqual({item["role"] for item in spec["assets"]}, {"background_video", "card_content"})
            staged_video = workspace / "input" / "synthetic-video.avi"
            self.assertEqual(staged_video.read_bytes()[:4], b"RIFF")
            self.assertTrue((workspace / "input" / "reference-card.png").exists())
        self.assertEqual(len(calls), 1)

    def test_myfonts_success_and_failure_flow_through_capability_adapter(self):
        analysis = fixture("reference_visual.json")
        attachment = [FIXTURES / "reference-card.png"]
        for response, expected_font, expected_confidence in (
            (fixture("myfonts_success.json"), "Source Serif 4 Semibold", "high"),
            (fixture("myfonts_failure.json"), None, "unresolved"),
        ):
            with self.subTest(expected_font=expected_font), tempfile.TemporaryDirectory() as folder:
                result = run(
                    "6 segundos. Presenta esta captura editorial.",
                    Path(folder) / "AE_Graphic_Lab",
                    attachments=attachment,
                    visual_analyzer=lambda _paths, data=analysis: data,
                    font_identifier=lambda _request, data=response: data,
                )
                self.assertEqual(result["STATIC_CHECK_OK"], "PASS")
                spec = json.loads(Path(result["artifacts_written"][0]).read_text(encoding="utf-8"))
                self.assertEqual(spec["typography"][0]["font"], expected_font)
                self.assertEqual(spec["typography"][0]["confidence"], expected_confidence)

    def test_graphic_spec_has_general_element_model_and_non_card_preset(self):
        schema = json.loads((PLUGIN_ROOT / "schemas" / "graphic-spec.schema.json").read_text(encoding="utf-8"))
        allowed = set(schema["properties"]["elements"]["items"]["properties"]["type"]["enum"])
        self.assertTrue({
            "text", "shape", "image", "video", "icon", "matte", "line",
            "panel", "group", "adjustment",
        }.issubset(allowed))
        spec = build_graphic_spec("5 segundos. Texto limpio con panel e icono.")
        self.assertEqual(spec["preset"]["id"], "title_panel")
        self.assertFalse(any(item["label"].startswith("CARD") for item in spec["elements"]))
        self.assertTrue({"text", "panel", "icon"}.issubset({item["type"] for item in spec["elements"]}))

    def test_shape_size_reveal_is_connected_to_rectangle_size_and_stable_origin(self):
        spec = build_graphic_spec("6 segundos. Tarjeta editorial con dos subrayados azules.")
        reveals = [item for item in spec["animation"] if item["property"] == "shape_size"]
        self.assertEqual(len(reveals), 2)
        self.assertTrue(all(item["start_value"][0] == 0 and item["origin"] == "left" for item in reveals))
        jsx = generate_jsx(spec)
        self.assertIn('rectanglePathProperty(animation.element, "ADBE Vector Rect Size")', jsx)
        self.assertIn('rectanglePathProperty(animation.element, "ADBE Vector Rect Position")', jsx)
        self.assertIn('(sizeValue[0] - finalSize[0]) / 2', jsx)

    def test_rounded_raster_has_real_track_matte(self):
        spec = build_graphic_spec("6 segundos. Presenta la captura.", fixture("reference_visual.json"))
        content = next(item for item in spec["elements"] if item["id"] == "card_content")
        matte = next(item for item in spec["elements"] if item["id"] == content["matte_id"])
        self.assertEqual(matte["type"], "matte")
        self.assertGreater(matte["geometry"]["roundness"], 0)
        jsx = generate_jsx(spec)
        self.assertIn("layer.setTrackMatte(matteLayer, TrackMatteType.ALPHA)", jsx)
        self.assertIn("layer.trackMatteLayer !== matteLayer", jsx)

    def test_paragraph_and_point_text_remain_distinct(self):
        paragraph = build_graphic_spec("5 segundos. Texto con panel e icono.")
        title = next(item for item in paragraph["elements"] if item["type"] == "text")
        self.assertEqual(title["text_mode"], "paragraph")
        self.assertGreater(title["text_box"]["width"], 0)
        paragraph_jsx = generate_jsx(paragraph)
        self.assertIn("layers.addBoxText([box.width, box.height])", paragraph_jsx)
        self.assertIn("sourceRectAtTime(0, false)", paragraph_jsx)

        custom = {
            "preset": {"id": "custom"},
            "elements": [{
                "id": "caption", "label": "CAPTION", "type": "text",
                "geometry": {"position": [960, 540], "size": [600, 80]},
                "appearance": {"color": "#FFFFFF", "opacity": 100, "text": "Punto"},
                "layer_order": 1,
            }],
            "typography": [{
                "element": "caption", "font": None, "confidence": "unresolved",
                "fallback": "ArialMT", "size": 48, "leading": 56, "tracking": 0,
                "alignment": "left", "provider": "fallback",
            }],
        }
        point = build_graphic_spec("3 segundos. Texto puntual.", custom)
        self.assertNotEqual(point["elements"][0].get("text_mode"), "paragraph")
        point_jsx = generate_jsx(point)
        self.assertIn('layer = STATE.comp.layers.addText(definition.appearance.text || "")', point_jsx)

    def test_ease_types_and_overshoot_generate_different_behavior(self):
        jsx = generate_jsx(build_graphic_spec("5 segundos. Texto con panel e icono."))
        self.assertIn('if (easing.type === "ease_in")', jsx)
        self.assertIn('firstOut = strong;', jsx)
        self.assertIn('} else if (easing.type === "ease_out")', jsx)
        self.assertIn('lastIn = strong;', jsx)
        self.assertIn('} else if (easing.type === "ease_in_out")', jsx)
        self.assertIn("property.setValueAtTime(overshootTime, overshootValue", jsx)

    def test_shared_essential_graphics_control_is_mastered(self):
        spec = build_graphic_spec("6 segundos. Tarjeta con dos subrayados azules.")
        control = next(item for item in spec["essential_graphics"] if item["id"] == "highlight_color")
        self.assertEqual(control["targets"], ["hl_01", "hl_02"])
        self.assertIs(control["master"], True)
        jsx = generate_jsx(spec)
        self.assertIn('effects.addProperty("ADBE Color Control")', jsx)
        self.assertIn("targetProperty.expression", jsx)

    def test_assets_have_explicit_roles_and_element_references(self):
        analysis = fixture("editorial_visual_analysis.json")
        analysis["assets"] = [
            {"id": "background", "role": "background_video", "source": "synthetic-video.avi", "required": True},
            {"id": "capture", "role": "card_content", "source": "reference-card.png", "required": True},
            {"id": "brand", "role": "logo", "source": "icon-reference.png", "required": False},
        ]
        spec = build_graphic_spec("6 segundos. Tarjeta editorial.", analysis)
        bg = next(item for item in spec["elements"] if item["id"] == "bg_media")
        content = next(item for item in spec["elements"] if item["id"] == "card_content")
        self.assertEqual(bg["asset_id"], "background")
        self.assertEqual(content["asset_id"], "capture")
        self.assertNotEqual(bg["asset_id"], content["asset_id"])

    def test_dependency_check_uses_runtime_snapshot_not_private_paths(self):
        source = (PLUGIN_ROOT / "scripts" / "check_dependencies.py").read_text(encoding="utf-8")
        self.assertNotIn("Path.home()", source)
        self.assertNotIn('".codex"', source)
        deferred = dependency_report()
        self.assertEqual(deferred["runtime_capabilities"]["myfonts"]["status"], "NOT_TESTED")
        observed = dependency_report([
            "mcp__codex_apps__myfonts_detect_font_regions",
            "premiere-jsx-script-creator",
        ])
        self.assertEqual(observed["runtime_capabilities"]["myfonts"]["status"], "PASS")
        self.assertEqual(observed["runtime_capabilities"]["premiere-jsx-script-creator"]["status"], "PASS")

    def test_two_distinct_end_to_end_fixtures(self):
        cases = [
            (
                "6 segundos. Tarjeta editorial con fondo de video, captura, blur y dos subrayados.",
                "editorial_visual_analysis.json",
                None,
                "editorial_card",
            ),
            (
                "5 segundos. Panel informativo con icono, cifra y texto secundario; anima cada parte de forma independiente.",
                "non_editorial_visual_analysis.json",
                [FIXTURES / "icon-reference.png"],
                "custom",
            ),
        ]
        for request, analysis_name, attachments, preset in cases:
            with self.subTest(preset=preset), tempfile.TemporaryDirectory() as folder:
                workspace = Path(folder) / "AE_Graphic_Lab"
                if attachments is None:
                    attachments = [
                        make_uncompressed_avi(Path(folder) / "synthetic-video.avi"),
                        FIXTURES / "reference-card.png",
                    ]
                result = run(
                    request,
                    workspace,
                    attachments=attachments,
                    visual_analyzer=lambda _paths, name=analysis_name: fixture(name),
                )
                self.assertEqual(result["GRAPHIC_SPEC_READY"], "PASS")
                self.assertEqual(result["JSX_GENERATED"], "PASS")
                self.assertEqual(result["STATIC_CHECK_OK"], "PASS")
                spec = json.loads((workspace / "output" / "GRAPHIC_SPEC.json").read_text(encoding="utf-8"))
                self.assertEqual(spec["preset"]["id"], preset)
                if preset == "editorial_card":
                    self.assertTrue(any(item.get("matte_id") for item in spec["elements"]))
                else:
                    labels = {item["label"] for item in spec["elements"]}
                    self.assertFalse(any(
                        label == "TITLE" or label.startswith("CARD") or label.startswith("HL_")
                        for label in labels
                    ))
                    self.assertTrue({"DATA_PANEL", "ICON", "METRIC", "CAPTION"}.issubset(labels))
                    animated = {item["element"] for item in spec["animation"]}
                    self.assertTrue({"data_panel", "info_icon", "metric", "caption"}.issubset(animated))


if __name__ == "__main__":
    unittest.main()
