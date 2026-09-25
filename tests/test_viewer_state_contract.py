"""Viewer state contracts (Stage 6).

These contracts drive the real generated viewer HTML inside jsdom and assert on
observable behaviour: classes, localStorage and recorded calls. This is the only
layer that can tell "a manual fold survives a reload" from "it is silently
lost", which is why the viewer state machine is not locked with static source
assertions (see docs/ARCHITECTURE.md).

The expectations live in tests/js/viewer.test.js. Contracts that are still
broken are marked "xfail" there, STRICTLY: when one starts passing the JS suite
fails, so its marker has to be flipped to "pass". That mirrors the
xfail(strict=True) discipline used by the Python contracts.

The JS layer needs its own dependency (jsdom), installed in tests/js so it
never reaches the packaged EXE: packaging/MarkdownReader.spec collects only
gui/assets, viewer, themes, templates/index and node_renderer. When that layer is not installed the
module skips with an explicit reason instead of failing.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from viewer_payload import write_viewer_payload  # noqa: E402

import core.converter as converter  # noqa: E402

JS_DIR = ROOT / "tests" / "js"
CONFIG = {"template": "modern", "numbering": True, "overwrite": True}

# Locked counts. They make a vanished or renamed contract a failure instead of
# a silent reduction of coverage.
EXPECTED_PASS = 22
EXPECTED_XFAIL = 0
EXPECTED_CONTRACTS = 22

# One document that deliberately exercises, per contract family:
#   * five heading levels, for the fold baseline and level contracts (F/M/N/P)
#   * a table, so the liveness sentinel proves the module set really ran
#   * four number forms where core/toc.py and the viewer regex disagree:
#       "一、乙组"   Python: numbered   viewer: missed
#       "1．2 丁组"  Python: numbered   viewer: missed (full-width dot)
#       "第1章 丙"   Python: numbered   viewer: missed (Arabic numerals)
#       "2）楔子"    Python: unnumbered viewer: marked by mistake
#   * "丙一子项" stays hidden across a toggle, which is what the one-pass
#     reconcile contract (P1) observes.
DOCUMENT_A = """# 1 首章

## 1.1 甲组

### 1.1.1 甲一

#### 甲一子项

### 一、乙组

#### 乙一子项

##### 乙一深项

## 1．2 丁组

### 第1章 丙

#### 丙一子项

### 2）楔子

## 无编号章

| a | b |
|---|---|
| 1 | 2 |
"""

# Same file name, different directory: both documents share a title, which is
# the precondition for the document-identity contract (D1).
DOCUMENT_B = """# 另一篇文档

正文。
"""


def _js_harness_reason() -> str:
    """Return "" when the jsdom layer can run, otherwise a skip reason."""
    if shutil.which("node") is None:
        return "Node.js is not on PATH, so the viewer contracts cannot run."
    if not (JS_DIR / "viewer.test.js").is_file():
        return "tests/js/viewer.test.js is missing."
    if not (JS_DIR / "node_modules" / "jsdom").is_dir():
        return "jsdom is not installed; run: cd tests/js && npm ci"
    return ""


pytestmark = pytest.mark.skipif(
    bool(_js_harness_reason()), reason=_js_harness_reason() or "jsdom layer unavailable"
)


def _convert(directory: Path, markdown: str) -> Path:
    """Convert one fixture document and return the generated HTML path."""
    source = directory / "README.md"
    source.write_text(markdown, encoding="utf-8")
    output = directory / "README.html"
    result = converter.process_single(str(source), str(output), CONFIG)
    if result is None:
        raise RuntimeError("conversion produced no output for " + str(source))
    return output


@pytest.fixture(scope="module")
def viewer_fixtures(tmp_path_factory) -> dict:
    """Build the two fixture documents once for the whole module."""
    root = tmp_path_factory.mktemp("viewer")
    documents = {}
    for variant, markdown in (("A", DOCUMENT_A), ("B", DOCUMENT_B)):
        directory = root / variant
        directory.mkdir(parents=True, exist_ok=True)
        documents[variant] = _convert(directory, markdown)

    # jsdom refuses localStorage for file:// URLs (opaque origin), so the
    # fixtures are opened through a loopback URL while keeping the real
    # Windows path in location.pathname, which is the identity under test.
    urls = {
        variant: "http://localhost/" + path.as_posix().lstrip("/")
        for variant, path in documents.items()
    }
    return {"paths": documents, "urls": urls}


def test_viewer_state_contracts(viewer_fixtures: dict, tmp_path: Path):
    """Run the jsdom contract suite and enforce its reported outcome."""
    environment = dict(os.environ)
    environment.update(
        {
            "MR_VIEWER_JS": str(write_viewer_payload(tmp_path)),
            "MR_FIXTURE_A": str(viewer_fixtures["paths"]["A"]),
            "MR_FIXTURE_A_URL": viewer_fixtures["urls"]["A"],
            "MR_FIXTURE_B": str(viewer_fixtures["paths"]["B"]),
            "MR_FIXTURE_B_URL": viewer_fixtures["urls"]["B"],
        }
    )
    completed = subprocess.run(
        ["node", "--test", "viewer.test.js"],
        cwd=str(JS_DIR),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (completed.stdout or "") + (completed.stderr or "")

    # The runner emits one synchronous line per contract; count them here rather
    # than trusting a summary printed at process exit. A truncated or crashed
    # run then shows up as a missing record instead of a smaller green suite,
    # and no reliance on stdout flushing inside an exit handler is needed. The
    # pattern is deliberately not anchored to the start of a line: the Node test
    # runner may prefix forwarded output.
    statuses = re.findall(r"CONTRACT (pass|xfail|xpass|fail) (.*)", output)
    assert len(statuses) == EXPECTED_CONTRACTS, (
        "expected " + str(EXPECTED_CONTRACTS) + " contract records but saw "
        + str(len(statuses)) + ":\n" + output
    )

    counts = Counter(status for status, _name in statuses)
    print("JS_CONTRACTS " + json.dumps({
        name: counts[name] for name in ("pass", "xfail", "xpass", "fail")
    }))
    print("JS_CONTRACT_RECORDS " + str(len(statuses)) + " of " + str(EXPECTED_CONTRACTS))
    assert counts["xpass"] == 0, (
        "a contract marked xfail now holds: flip its marker to \"pass\" in "
        "tests/js/viewer.test.js:\n" + output
    )
    assert counts["fail"] == 0, "a contract marked pass failed:\n" + output
    assert counts["pass"] == EXPECTED_PASS, output
    assert counts["xfail"] == EXPECTED_XFAIL, output
    assert completed.returncode == 0, output
