"""Phase 12 GUI closeout: preview and carry are two different states.

The theme model on the main page was rebuilt around that split, and the expectations live in
`tests/js/gui_preview.test.js`:

* a preview is a session-only view of a theme (builtin or installed), driven by the theme
  navigation and by clicking a row body;
* a carry selection is what the next document embeds, driven only by the row checkbox, and it is
  the only theme state that reaches config.json.

This wrapper runs that suite and enforces its own record count, exactly the way
`test_gui_state_contract.py` does for `gui.test.js`. The two files are kept apart on purpose:
gui.test.js continues to lock the 49 records that describe the older GUI surfaces (inputs,
conversion, carry persistence, settings, removal), so a reader can tell which contract belongs to
which product model -- and a change in one count never silently rewrites the other.
"""

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

# Phase 12 GUI closeout adds GP1-GP14. During the red phase the suite reports failures instead of
# the passes below; these numbers are the green target the lock enforces.
EXPECTED_PASS = 14
EXPECTED_XFAIL = 0
EXPECTED_CONTRACTS = 14


def _gui_harness_reason() -> str:
    """Return "" when the jsdom layer can run, otherwise an explicit reason."""
    if shutil.which("node") is None:
        return "Node.js is not on PATH, so the GUI contracts cannot run."
    if not (JS_DIR / "gui_preview.test.js").is_file():
        return "tests/js/gui_preview.test.js is missing."
    if not (JS_DIR / "node_modules" / "jsdom").is_dir():
        return "jsdom is not installed; run: cd tests/js && npm ci"
    return ""


pytestmark = pytest.mark.skipif(
    bool(_gui_harness_reason()), reason=_gui_harness_reason() or "jsdom layer unavailable"
)


def test_gui_preview_contracts():
    """Run the jsdom preview suite and enforce its reported outcome."""
    environment = dict(os.environ)
    environment.update({"MR_GUI_HTML": str(GUI_HTML), "MR_GUI_JS": str(GUI_JS)})
    completed = subprocess.run(
        ["node", "--test", "gui_preview.test.js"],
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
    print("GUI_PREVIEW_CONTRACTS " + json.dumps({
        name: counts[name] for name in ("pass", "xfail", "xpass", "fail")
    }))
    print("GUI_PREVIEW_CONTRACT_RECORDS " + str(len(statuses)) + " of " + str(EXPECTED_CONTRACTS))
    assert counts["xpass"] == 0, (
        "a contract marked xfail now holds: flip its marker to pass in "
        "tests/js/gui_preview.test.js:\n" + output
    )
    assert counts["fail"] == 0, "a contract marked pass failed:\n" + output
    assert counts["pass"] == EXPECTED_PASS, output
    assert counts["xfail"] == EXPECTED_XFAIL, output
    assert completed.returncode == 0, output
