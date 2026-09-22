"""Harness self-checks (Stage 7.1).

These checks are about the jsdom harness itself, never about the viewer page. The
viewer layer read page errors from an override of window.console.error only, which
is blind to an exception thrown inside a DOM listener, because jsdom reports those
on its virtual console. SC2 was red before the fix; SC1 records the historical gap
that makes a second channel necessary.

The checks live in tests/js/harness_selfcheck.test.js and report "SELFCHECK"
lines, deliberately distinct from the viewer suite's "CONTRACT" lines, so this
module can never change the viewer record count.

harness.mjs reads MR_VIEWER_JS at import time, so it is provided here even though
the checks build their own minimal pages and never touch the viewer fixtures.
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
VIEWER_JS = ROOT / "templates" / "viewer.js"

# Locked count: a vanished or renamed check must fail instead of quietly reducing
# coverage.
EXPECTED_CHECKS = 5


def _js_harness_reason() -> str:
    """Return "" when the jsdom layer can run, otherwise a skip reason."""
    if shutil.which("node") is None:
        return "Node.js is not on PATH, so the harness self-checks cannot run."
    if not (JS_DIR / "harness_selfcheck.test.js").is_file():
        return "tests/js/harness_selfcheck.test.js is missing."
    if not (JS_DIR / "node_modules" / "jsdom").is_dir():
        return "jsdom is not installed; run: cd tests/js && npm ci"
    return ""


pytestmark = pytest.mark.skipif(
    bool(_js_harness_reason()), reason=_js_harness_reason() or "jsdom layer unavailable"
)


def test_harness_self_checks():
    """Run the harness self-checks and enforce their reported outcome."""
    environment = dict(os.environ)
    environment.update({"MR_VIEWER_JS": str(VIEWER_JS)})
    completed = subprocess.run(
        ["node", "--test", "harness_selfcheck.test.js"],
        cwd=str(JS_DIR),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (completed.stdout or "") + (completed.stderr or "")

    # Count the per-check lines rather than trusting a summary printed at process
    # exit, so a truncated or crashed run shows up as a missing record.
    records = re.findall(r"SELFCHECK (pass|fail) (.*)", output)
    assert len(records) == EXPECTED_CHECKS, (
        "expected " + str(EXPECTED_CHECKS) + " self-check records but saw "
        + str(len(records)) + ":\n" + output
    )

    counts = Counter(status for status, _name in records)
    print("SELFCHECK_RECORDS " + str(len(records)) + " of " + str(EXPECTED_CHECKS))
    print("SELFCHECK " + json.dumps({"pass": counts["pass"], "fail": counts["fail"]}))
    assert counts["fail"] == 0, "a harness self-check failed:\n" + output
    assert completed.returncode == 0, output
