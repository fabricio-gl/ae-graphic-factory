"""Run the emitted ES3 JSX against an intentionally strict AE API test double."""
import copy
import json
import math
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from aegf.ae_jsx import generate_jsx
from aegf.graphic_spec import build_graphic_spec, validate_graphic_spec, parse_timing_and_format
from aegf.schema_validation import validate_graphic_spec_schema, validate_instance
from aegf.static_validation import validate_jsx


def acceptance():
    analysis = json.loads((ROOT / "tests/fixtures/acceptance_av.json").read_text(encoding="utf-8"))
    return build_graphic_spec("5 s, 1920x1080, 30 fps. Entrada, salida y fundido de audio en los últimos 15 fotogramas.", analysis)


def media_options():
    return {
        "files": {"/input/background.png": {}, "/input/portrait.avi": {}},
        "metadata": {
            "/input/background.png": {"width": 1920, "height": 1080, "hasVideo": True, "hasAudio": False, "duration": 0, "mainSource": {"isStill": True}},
            "/input/portrait.avi": {"width": 108, "height": 192, "hasVideo": True, "hasAudio": True, "duration": 5, "mainSource": {"isStill": False}},
        },
    }


def execute(source, options=None):
    node = shutil.which("node")
    if not node:
        raise AssertionError("Node requerido para pruebas automatizadas de contratos; no omitirlas.")
    proc = subprocess.run([node, str(ROOT / "tests/ae_host_double.js")],
                          input=json.dumps({"source": source, "options": options or {}}),
                          capture_output=True, text=True, encoding="utf-8", timeout=15)
    if proc.returncode:
        raise AssertionError(proc.stderr)
    return json.loads(proc.stdout)


def states(result):
    content = result["files"].get("/output/ae_graphic_factory.log", {}).get("data", "")
    return dict(line.split("=", 1) for line in content.split("---")[0].splitlines() if "=" in line)


def events(result, name):
    return [e for e in result["events"] if e["name"] == name]


class RuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.spec = acceptance()
        self.source = generate_jsx(self.spec)
        self.options = media_options()

    def test_acceptance_full_execution_in_double_not_adobe(self):
        result = execute(self.source, self.options)
        self.assertNotIn("uncaught", result)
        self.assertEqual(states(result)["AEP_SAVE_OK"], "PASS", result["logs"])
        self.assertEqual(states(result)["MOGRT_EXPORT_OK"], "PASS", result["logs"])
        self.assertEqual(events(result, "export")[0]["value"], 1)
        names = [e["name"] for e in result["events"]]
        self.assertLess(names.index("save"), names.index("export"))
        self.assertEqual(next(p["value"] for p in result["properties"] if p["matchName"] == "ADBE Gaussian Blur 2-0001"), 80)

    def test_spatial_position_2d_uses_one_ease_and_opacity_scalar_one(self):
        result = execute(self.source, self.options)
        for name in ("ADBE Position", "ADBE Opacity"):
            props = [p for p in result["properties"] if p["matchName"] == name and p["eases"]]
            self.assertTrue(props)
            for p in props:
                self.assertTrue(all(len(e["incoming"]) == len(e["outgoing"]) == 1 for e in p["eases"]))

    def test_nonspatial_scale_uses_two_eases_and_color_uses_one(self):
        spec = build_graphic_spec("5 s. Texto con panel e icono.")
        spec["animation"].append(dict(element="panel", property="color", start_frame=0, end_frame=15,
            start_value="#000000", end_value="#FFFFFF", interpolation="bezier",
            easing={"type": "ease_in_out", "influence": 60, "overshoot": False}, motion_blur=False))
        result = execute(generate_jsx(spec))
        self.assertEqual(states(result)["AEP_SAVE_OK"], "PASS", result["logs"])
        for name, n in (("ADBE Scale", 2), ("ADBE Vector Fill Color", 1)):
            props = [p for p in result["properties"] if p["matchName"] == name and p["eases"]]
            self.assertTrue(props)
            self.assertTrue(all(len(e["incoming"]) == n for p in props for e in p["eases"]))

    def test_point_and_paragraph_text_use_distinct_ae_constructors(self):
        reference = json.loads((ROOT / "tests/fixtures/non_editorial_visual_analysis.json").read_text(encoding="utf-8"))
        spec = build_graphic_spec(
            "5 segundos. Panel informativo con cifra y texto secundario.",
            reference,
        )
        options = {
            "files": {"/input/icon-reference.png": {}},
            "metadata": {
                "/input/icon-reference.png": {
                    "width": 64,
                    "height": 64,
                    "hasVideo": True,
                    "hasAudio": False,
                    "duration": 0,
                    "mainSource": {"isStill": True},
                }
            },
        }
        result = execute(generate_jsx(spec), options)
        self.assertEqual(states(result)["AEP_SAVE_OK"], "PASS", result["logs"])
        self.assertEqual(len(events(result, "addText")), 1)
        self.assertEqual(len(events(result, "addBoxText")), 1)

    def test_shape_size_and_rounded_matte_execute_in_contract_double(self):
        reference = json.loads((ROOT / "tests/fixtures/reference_visual.json").read_text(encoding="utf-8"))
        spec = build_graphic_spec("6 segundos. Presenta la captura con un subrayado.", reference)
        options = {
            "files": {"/input/reference-card.png": {}},
            "metadata": {
                "/input/reference-card.png": {
                    "width": 160,
                    "height": 90,
                    "hasVideo": True,
                    "hasAudio": False,
                    "duration": 0,
                    "mainSource": {"isStill": True},
                }
            },
        }
        result = execute(generate_jsx(spec), options)
        self.assertEqual(states(result)["AEP_SAVE_OK"], "PASS", result["logs"])
        self.assertEqual(len(events(result, "trackMatte")), 1)
        size = next(
            prop for prop in result["properties"]
            if prop["matchName"] == "ADBE Vector Rect Size" and len(prop["keys"]) == 2
        )
        position = next(
            prop for prop in result["properties"]
            if prop["matchName"] == "ADBE Vector Rect Position" and len(prop["keys"]) == 2
        )
        self.assertEqual(size["keys"][0]["value"][0], 0)
        self.assertGreater(size["keys"][1]["value"][0], 0)
        self.assertLess(position["keys"][0]["value"][0], position["keys"][1]["value"][0])

    def test_ease_in_and_ease_out_have_opposite_temporal_influences(self):
        reference = {
            "preset": {"id": "custom"},
            "elements": [
                {"id": "left", "label": "LEFT", "type": "shape",
                 "geometry": {"position": [700, 540], "size": [200, 80]},
                 "appearance": {"color": "#FFFFFF", "opacity": 100}, "layer_order": 1},
                {"id": "right", "label": "RIGHT", "type": "shape",
                 "geometry": {"position": [1220, 540], "size": [200, 80]},
                 "appearance": {"color": "#FFFFFF", "opacity": 100}, "layer_order": 2},
            ],
            "animation": [
                {"element": "left", "property": "opacity", "start_frame": 0, "end_frame": 15,
                 "start_value": 0, "end_value": 100, "interpolation": "bezier",
                 "easing": {"type": "ease_in", "influence": 70, "overshoot": False}, "motion_blur": False},
                {"element": "right", "property": "opacity", "start_frame": 0, "end_frame": 15,
                 "start_value": 0, "end_value": 100, "interpolation": "bezier",
                 "easing": {"type": "ease_out", "influence": 70, "overshoot": False}, "motion_blur": False},
            ],
            "essential_graphics": [
                {"label": "Color izquierdo", "property": "fill_color", "targets": ["left"], "purpose": "Color"},
                {"label": "Color derecho", "property": "fill_color", "targets": ["right"], "purpose": "Color"},
            ],
        }
        result = execute(generate_jsx(build_graphic_spec("2 segundos.", reference)))
        animated = [
            prop for prop in result["properties"]
            if prop["matchName"] == "ADBE Opacity" and len(prop["keys"]) == 2
        ]
        patterns = {
            (
                prop["eases"][0]["outgoing"][0]["influence"],
                prop["eases"][1]["incoming"][0]["influence"],
            )
            for prop in animated
        }
        self.assertIn((70, 16.667), patterns)
        self.assertIn((16.667, 70), patterns)

    def test_audio_gain_last_15_frame_intervals(self):
        result = execute(self.source, self.options)
        levels = next(p for p in result["properties"] if p["matchName"] == "ADBE Audio Levels")
        self.assertEqual(len(levels["keys"]), 16)
        self.assertEqual(levels["keys"][0]["time"], 4.5)
        self.assertEqual(levels["keys"][-1]["time"], 5.0)
        self.assertEqual(levels["keys"][0]["value"], [0, 0])
        self.assertEqual(levels["keys"][-1]["value"], [-192, -192])
        middle = levels["keys"][5]["value"]
        self.assertAlmostEqual(middle[0], 20 * math.log10(2 / 3))
        self.assertEqual(middle[0], middle[1])
        self.assertTrue(all(k["interpolation"] == ["LINEAR", "LINEAR"] for k in levels["keys"]))

    def test_wrong_selection_jsx_rejected_before_import_or_mutation(self):
        self.options["files"].pop("/input/portrait.avi")
        self.options["files"]["/input/crear_grafico.jsx"] = {}
        self.options["selection"] = "/input/crear_grafico.jsx"
        self.options["env"] = {"AEGF_HEADLESS": "0"}
        result = execute(self.source, self.options)
        self.assertFalse(events(result, "import"))
        self.assertFalse(events(result, "begin"))
        self.assertIn("formato .jsx no compatible", " ".join(result["logs"]))
        self.assertIn("rol video; esperado portrait.avi", " ".join(result["logs"]))
        self.assertIn("portrait.avi", events(result, "dialog")[0]["value"]["filter"])

    def test_wrong_name_even_if_extension_allowed(self):
        self.options["files"].pop("/input/portrait.avi")
        self.options["files"]["/input/another.avi"] = {}
        self.options.update(selection="/input/another.avi", env={"AEGF_HEADLESS": "0"})
        result = execute(self.source, self.options)
        self.assertFalse(events(result, "import"))
        self.assertIn("se seleccionó another.avi", " ".join(result["logs"]))

    def test_missing_or_empty_media_prevents_project_changes(self):
        for value in (None, {"length": 0}):
            with self.subTest(value=value):
                options = media_options()
                if value is None:
                    options["files"].pop("/input/portrait.avi")
                else:
                    options["files"]["/input/portrait.avi"] = value
                result = execute(self.source, options)
                self.assertFalse(events(result, "import"))
                self.assertFalse(events(result, "comp"))
                self.assertEqual(states(result)["PREFLIGHT_OK"], "FAIL")

    def test_metadata_failures_rollback_imports_before_layer_construction(self):
        for field, value in (("hasVideo", False), ("hasAudio", False), ("width", 0),
                             ("width", 192), ("height", 108), ("duration", 4.9),
                             ("duration", 0), ("mainSource", {"isStill": True})):
            with self.subTest(field=field, value=value):
                options = media_options()
                options["metadata"]["/input/portrait.avi"][field] = value
                result = execute(self.source, options)
                self.assertFalse(events(result, "comp"), result["logs"])
                self.assertEqual(states(result)["MEDIA_PREFLIGHT_OK"], "FAIL")
                self.assertEqual(states(result)["ROLLBACK_OK"], "PASS")
                self.assertEqual(result["remainingItems"], 0)
                self.assertFalse(events(result, "save"))

    def test_bad_codec_and_null_import_are_actionable(self):
        for option in ("cannotImport", "importThrow", "importNull"):
            with self.subTest(option=option):
                options = media_options()
                options[option] = True
                result = execute(self.source, options)
                self.assertEqual(states(result)["MEDIA_PREFLIGHT_OK"], "FAIL")
                self.assertFalse(events(result, "comp"))
                self.assertIn("rol background_image", " ".join(result["logs"]))

    def test_controllers_must_be_supported_added_and_counted(self):
        for option in ("controllerUnsupported", "controllerReject", "controllerLie"):
            with self.subTest(option=option):
                options = media_options()
                options[option] = True
                result = execute(self.source, options)
                self.assertFalse(events(result, "export"))
                self.assertFalse(events(result, "save"))
                self.assertEqual(states(result)["AEP_BUILD_OK"], "FAIL")
                self.assertEqual(result["remainingItems"], 0)

    def test_runtime_rejects_tampered_empty_controls(self):
        source = self.source.replace(json.dumps(self.spec, ensure_ascii=True, separators=(",", ":")),
                                     json.dumps(dict(self.spec, essential_graphics=[]), ensure_ascii=True, separators=(",", ":")))
        result = execute(source, self.options)
        self.assertFalse(events(result, "begin"))
        self.assertFalse(events(result, "export"))
        self.assertEqual(states(result)["PREFLIGHT_OK"], "FAIL")

    def test_export_failure_keeps_saved_aep_and_reports_separate_states(self):
        for option in ("exportThrow", "exportReject", "exportMissing"):
            with self.subTest(option=option):
                options = media_options()
                options[option] = True
                result = execute(self.source, options)
                status = states(result)
                self.assertEqual(status["AEP_BUILD_OK"], "PASS")
                self.assertEqual(status["AEP_SAVE_OK"], "PASS")
                self.assertEqual(status["AE_RUNTIME_OK"], "PASS")
                self.assertEqual(status["MOGRT_EXPORT_OK"], "FAIL")
                self.assertEqual(status["ROLLBACK_OK"], "NOT_APPLICABLE")
                self.assertTrue(result["remainingItems"])
                self.assertFalse(result["removed"])
                self.assertIn("AEP guardado y conservado", " ".join(result["logs"]))

    def test_save_failure_rolls_back_without_export(self):
        for option in ("saveThrow", "saveMissing"):
            options = media_options()
            options[option] = True
            result = execute(self.source, options)
            self.assertEqual(states(result)["AEP_SAVE_OK"], "FAIL")
            self.assertEqual(states(result)["ROLLBACK_OK"], "PASS")
            self.assertEqual(result["remainingItems"], 0)
            self.assertFalse(events(result, "export"))

    def test_preexisting_project_never_closed_or_rolled_back(self):
        self.options.update(existingProject=True, env={"AEGF_QUIT_AFTER_RUN": "1"})
        result = execute(self.source, self.options)
        for name in ("begin", "end", "import", "save", "close", "quit"):
            self.assertFalse(events(result, name))
        self.assertFalse(result["removed"])

    def test_existing_outputs_not_overwritten_or_treated_as_success(self):
        self.options["files"]["/output/grafico.aep"] = {"length": 55}
        result = execute(self.source, self.options)
        self.assertFalse(events(result, "save"))
        self.assertEqual(result["files"]["/output/grafico.aep"]["length"], 55)
        self.assertEqual(states(result)["AEP_SAVE_OK"], "NOT_TESTED")

    def test_aep_only_needs_no_dummy_controller(self):
        self.spec["exports"]["mogrt"] = False
        self.spec["essential_graphics"] = []
        result = execute(generate_jsx(self.spec), self.options)
        self.assertEqual(states(result)["AEP_SAVE_OK"], "PASS", result["logs"])
        self.assertEqual(states(result)["MOGRT_EXPORT_OK"], "NOT_APPLICABLE")
        self.assertFalse(events(result, "export"))
        self.assertFalse(events(result, "addController"))

    def test_old_ease_mutant_is_detected_during_execution(self):
        mutant = self.source.replace('var dimensions = 1;', 'var dimensions = (property.value instanceof Array) ? property.value.length : 1;')
        result = execute(mutant, self.options)
        self.assertIn("AE_TEMPORAL_EASE_LENGTH", " ".join(result["logs"]))
        self.assertEqual(states(result)["AEP_BUILD_OK"], "FAIL")
        self.assertFalse(events(result, "save"))


class SchemaRegressionTests(unittest.TestCase):
    def setUp(self):
        self.spec = acceptance()

    def test_seconds_duration_not_overridden_by_audio_frame_count(self):
        self.assertEqual(self.spec["composition"]["frame_count"], 150)
        self.assertEqual(parse_timing_and_format("150 frames, 30 fps.")["frame_count"], 150)

    def test_export_empty_controls_fails_schema_and_semantics(self):
        for version in ("1.0.0", "1.1.0"):
            self.spec["schema_version"] = version
            self.spec["essential_graphics"] = []
            self.assertTrue(validate_graphic_spec_schema(self.spec))
            self.assertTrue(validate_graphic_spec(self.spec))
            with self.assertRaises(ValueError):
                generate_jsx(self.spec)
        self.spec["exports"]["mogrt"] = False
        self.assertEqual(validate_graphic_spec(self.spec), [])

    def test_legacy_1_0_spec_with_real_controller_still_works(self):
        old = json.loads((ROOT / "tests/fixtures/graphic_spec_valid.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_graphic_spec(old), [])
        self.assertEqual(states(execute(generate_jsx(old)))["MOGRT_EXPORT_OK"], "PASS")

    def test_meaningless_ambiguous_duplicate_controls_rejected(self):
        for control in (
            {"label": "Fake", "purpose": "Nothing"},
            {"label": "Fake", "purpose": "Nothing", "source_property": "MISSING.Source Text"},
            {"label": "Fake", "purpose": "Nothing", "property": "source_text", "targets": ["blur"]},
            {"label": "Fake", "purpose": "Nothing", "property": "blur", "targets": ["blur"], "source_property": "BLUR.Source Text"},
        ):
            with self.subTest(control=control):
                spec = copy.deepcopy(self.spec)
                spec["essential_graphics"] = [control]
                self.assertTrue(validate_graphic_spec(spec))
        self.spec["essential_graphics"] *= 2
        self.assertTrue(validate_graphic_spec(self.spec))

    def test_audio_limits_and_unsupported_semantics_rejected(self):
        for value in (-1, 101, True, [100, 100], float("nan")):
            spec = copy.deepcopy(self.spec)
            spec["animation"][-1]["end_value"] = value
            self.assertTrue(validate_graphic_spec_schema(spec))
        for field, value in (("interpolation", "bezier"), ("motion_blur", True)):
            spec = copy.deepcopy(self.spec)
            spec["animation"][-1][field] = value
            self.assertTrue(validate_graphic_spec(spec))
        self.spec["animation"][-1]["easing"]["overshoot"] = True
        self.assertTrue(validate_graphic_spec_schema(self.spec))

    def test_only_audio_may_use_composition_end_boundary(self):
        self.assertEqual(validate_graphic_spec(self.spec), [])
        self.spec["animation"][0]["end_frame"] = 150
        self.assertTrue(validate_graphic_spec(self.spec))

    def test_media_contract_rejects_extensions_roles_and_audio_contradictions(self):
        for key, value in (("source", "script.jsx"), ("source", "image.svg"),
                           ("source", "movie.webm"), ("role", "background_image"), ("required", False)):
            spec = copy.deepcopy(self.spec)
            spec["assets"][1][key] = value
            self.assertTrue(validate_graphic_spec(spec), (key, value))
        self.spec["assets"][1]["expected"]["has_audio"] = False
        self.assertTrue(validate_graphic_spec(self.spec))

    def test_explicit_empty_controls_are_not_silently_replaced(self):
        ref = {"elements": self.spec["elements"], "assets": self.spec["assets"], "essential_graphics": []}
        with self.assertRaises(ValueError):
            build_graphic_spec("5 s.", ref)

    def test_static_checks_reject_removed_guards(self):
        source = generate_jsx(self.spec)
        self.assertEqual(validate_jsx(source, strict=True)["errors"], [])
        for old, new in (("if (!property.isSpatial)", "if (true)"),
                         ("if (STATE.controllersAdded < 1", "if (0 < 1"),
                         ("validateAssetFile(asset, relative)", "log(relative)")):
            self.assertTrue(validate_jsx(source.replace(old, new))["errors"])

    def test_schema_conditionals_are_actually_enforced(self):
        rule = {"if": {"properties": {"export": {"const": True}}, "required": ["export"]},
                "then": {"properties": {"controls": {"minItems": 1}}}}
        self.assertTrue(validate_instance({"export": True, "controls": []}, rule))
        self.assertEqual(validate_instance({"export": False, "controls": []}, rule), [])


if __name__ == "__main__":
    unittest.main()
