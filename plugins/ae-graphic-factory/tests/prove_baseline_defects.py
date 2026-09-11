"""Reproduce all three reported defects in a supplied read-only old snapshot."""
import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from test_runtime_contracts import execute, events, states


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    code = """import json, sys
sys.path.insert(0, sys.argv[1])
from aegf.graphic_spec import build_graphic_spec
from aegf.ae_jsx import generate_jsx
spec = json.load(sys.stdin)
print(generate_jsx(spec))
"""
    fixture = Path(__file__).parent / "fixtures/graphic_spec_valid.json"
    baseline = json.loads(fixture.read_text(encoding="utf-8"))
    from aegf.ae_jsx import generate_jsx
    def old_source(spec):
        r = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", code, str(args.snapshot / "scripts")],
                           input=json.dumps(spec), capture_output=True, text=True, encoding="utf-8", timeout=15)
        if r.returncode:
            raise AssertionError(r.stderr)
        return r.stdout
    report = {}
    spec = copy.deepcopy(baseline)
    text_id = spec["elements"][0]["id"]
    spec["animation"] = [dict(element=text_id, property="position", start_frame=0, end_frame=15,
        start_value=[0, 0], end_value=[500, 500], interpolation="bezier",
        easing={"type": "ease_out", "influence": 70, "overshoot": False}, motion_blur=True)]
    old = execute(old_source(spec))
    new = execute(generate_jsx(spec))
    assert "AE_TEMPORAL_EASE_LENGTH" in old["files"]["/output/ae_graphic_factory.log"]["data"], old
    assert states(new)["AEP_SAVE_OK"] == "PASS", new["logs"]
    report["spatial_easing"] = {"old": "FAIL", "new": "PASS", "evidence": "AE_TEMPORAL_EASE_LENGTH on generated Position"}
    spec = copy.deepcopy(baseline)
    spec["essential_graphics"] = []
    spec["animation"] = []
    old = execute(old_source(spec))
    assert events(old, "export") and "AE_NO_CONTROLLERS" in old["files"]["/output/ae_graphic_factory.log"]["data"]
    try:
        generate_jsx(spec)
        raise AssertionError("New generator accepted MOGRT with no controls")
    except ValueError:
        pass
    report["zero_controllers"] = {"old": "FAIL", "new": "PASS", "evidence": "Old JSX reached export with controller count 0; new schema rejects"}
    spec = copy.deepcopy(baseline)
    spec["elements"] = [dict(id="clip", label="VIDEO", type="video", asset_id="clip",
        geometry={"position": [960, 540], "size": [500, 800]}, appearance={"opacity": 100}, layer_order=1)]
    spec["assets"] = [dict(id="clip", role="video", source="clip.avi", required=True, preserve_or_reconstruct="preserve")]
    spec["animation"] = []
    spec["typography"] = []
    spec["essential_graphics"] = [dict(label="Opacidad", property="opacity", targets=["clip"], purpose="Opacidad del video")]
    options = {"files": {"/input/script.jsx": {}}, "selection": "/input/script.jsx", "env": {"AEGF_HEADLESS": "0"}}
    old = execute(old_source(spec), options)
    new = execute(generate_jsx(spec), options)
    assert events(old, "import")[0]["value"] == "/input/script.jsx", old["logs"]
    assert not events(new, "import"), new["logs"]
    report["jsx_as_footage"] = {"old": "FAIL", "new": "PASS", "evidence": "Old JSX imported selected script.jsx; new JSX rejects before import"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"kind": "HOST_DOUBLE_NOT_ADOBE", "regressions": report}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
