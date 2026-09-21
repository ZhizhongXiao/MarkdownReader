"""GUI state contracts (Stage 6.6).

These contracts drive the real GUI (index.html + gui.js) in jsdom through a
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

JS_DIR = ROOT / "tests" / "js"
GUI_HTML = ROOT / "gui" / "assets" / "index.html"
GUI_JS = ROOT / "gui" / "assets" / "gui.js"
API_PY = ROOT / "gui" / "api.py"

# Locked counts: a vanished or renamed contract must fail instead of silently
# reducing coverage.
EXPECTED_PASS = 8
EXPECTED_XFAIL = 0
EXPECTED_CONTRACTS = 8


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


def test_gui_state_contracts():
    """Run the jsdom GUI contract suite and enforce its reported outcome."""
    environment = dict(os.environ)
    environment.update(
        {
            "MR_GUI_HTML": str(GUI_HTML),
            "MR_GUI_JS": str(GUI_JS),
            "MR_PREPARE_SINGLE_REQUEST": str(_single_request_shape("prepare_conversion")),
            "MR_CONVERT_SINGLE_REQUEST": str(_single_request_shape("convert")),
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
