"""GUI state contracts (Stage 6.6).

These contracts drive the real GUI (index.html + manifest-assembled script) in jsdom through a
controllable pywebview stub, and observe the DOM plus the recorded bridge calls.
They are the only place where the GUI state machine is exercised, because the
existing gui contract test only reads the sources as text.

GU1 is deliberately a JOINT contract: the JS call shape AND the Python bridge
signature. The signature is measured here, before Node starts, and handed over as
an environment variable, so there is exactly one contract record for it and the
pytest counting model stays "83 passed" with no extra xfail.

Expectations live in tests/js/gui.test.js. Contracts that are still broken are
marked "xfail" there, STRICTLY: when one starts passing the JS suite fails and
its marker must be flipped to "pass".
"""

import ast
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.app import load_gui_javascript  # noqa: E402

JS_DIR = ROOT / "tests" / "js"
GUI_HTML = ROOT / "gui" / "assets" / "index.html"
API_PY = ROOT / "gui" / "api.py"

# Locked counts: a vanished or renamed contract must fail instead of silently
# reducing coverage. Phase 9A adds GT1-GT18 (the external theme selection surface and
# the persistence-before-conversion ordering) to GU0-GU8, which is where 9 + 18 comes
# from; the GT13 freeze contract grew a second half without adding a record.
# Phase 9B1 adds 14 settings records (GS1-GS13 plus GS2b: inventory, import/remove/export/open,
# storage and about facts, the run lock and the joint call shapes).
# Phase 11 adds 7 records (GR1-GR7: the onefile-only entry, the promised items, the five
# second countdown on frozen time, cancel, the terminal lock, the single request, and the
# explicit-refusal recovery). Phase 9B2 adds GT19 (an installed broken theme is neither
# selectable nor removable, and the summary counts what it renders). During the red phase the
# suite reports the failures instead of the passes below. Phase 12 adds GU0b: the light/dark
# toggle keeps fixed SVG icon boxes while the mode changes; settings reuses the shared header.
# These are the green targets.
EXPECTED_PASS = 50
EXPECTED_XFAIL = 0
EXPECTED_CONTRACTS = 50


def _single_request_shape(method: str) -> int:
    """Return 1 only when the bridge method is self plus one request argument."""
    try:
        from gui.api import BridgeApi

        parameters = list(inspect.signature(getattr(BridgeApi, method)).parameters)
        return 1 if parameters[:1] == ["self"] and len(parameters) == 2 else 0
    except Exception:
        pass
    # Fall back to parsing the source: importing the GUI module can pull in
    # pywebview, which the existing GUI tests deliberately avoid as well.
    try:
        tree = ast.parse(API_PY.read_text(encoding="utf-8"))
    except Exception:
        return 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "BridgeApi":
            continue
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method:
                names = [argument.arg for argument in item.args.args]
                return 1 if names[:1] == ["self"] and len(names) == 2 else 0
    return 0


def _gui_harness_reason() -> str:
    """Return "" when the jsdom layer can run, otherwise an explicit reason."""
    if shutil.which("node") is None:
        return "Node.js is not on PATH, so the GUI contracts cannot run."
    if not (JS_DIR / "gui.test.js").is_file():
        return "tests/js/gui.test.js is missing."
    if not (JS_DIR / "node_modules" / "jsdom").is_dir():
        return "jsdom is not installed; run: cd tests/js && npm ci"
    return ""


pytestmark = pytest.mark.skipif(
    bool(_gui_harness_reason()), reason=_gui_harness_reason() or "jsdom layer unavailable"
)


def test_gui_state_contracts(tmp_path):
    """Run the jsdom GUI contract suite and enforce its reported outcome."""
    javascript_path = tmp_path / "gui.bundle.js"
    javascript_path.write_text(load_gui_javascript(), encoding="utf-8")
    environment = dict(os.environ)
    environment.update(
        {
            "MR_GUI_HTML": str(GUI_HTML),
            "MR_GUI_JS": str(javascript_path),
            "MR_PREPARE_SINGLE_REQUEST": str(_single_request_shape("prepare_conversion")),
            "MR_CONVERT_SINGLE_REQUEST": str(_single_request_shape("convert")),
            # Phase 9B1: the settings page sends one request dict for the two actions
            # whose target the bridge itself has to ask for.
            "MR_IMPORT_SINGLE_REQUEST": str(_single_request_shape("import_theme")),
            "MR_EXPORT_SINGLE_REQUEST": str(_single_request_shape("export_theme_template")),
        }
    )
    completed = subprocess.run(
        ["node", "--test", "gui.test.js"],
        cwd=str(JS_DIR),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (completed.stdout or "") + (completed.stderr or "")

    statuses = re.findall(r"CONTRACT (pass|xfail|xpass|fail) (.*)", output)
    assert len(statuses) == EXPECTED_CONTRACTS, (
        "expected " + str(EXPECTED_CONTRACTS) + " contract records but saw "
        + str(len(statuses)) + ":\n" + output
    )

    counts = Counter(status for status, _name in statuses)
    print("GUI_CONTRACTS " + json.dumps({
        name: counts[name] for name in ("pass", "xfail", "xpass", "fail")
    }))
    print("GUI_CONTRACT_RECORDS " + str(len(statuses)) + " of " + str(EXPECTED_CONTRACTS))
    assert counts["xpass"] == 0, (
        "a contract marked xfail now holds: flip its marker to pass in tests/js/gui.test.js:\n"
        + output
    )
    assert counts["fail"] == 0, "a contract marked pass failed:\n" + output
    assert counts["pass"] == EXPECTED_PASS, output
    assert counts["xfail"] == EXPECTED_XFAIL, output
    assert completed.returncode == 0, output
