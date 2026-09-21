"""Index page state contracts (Stage 6.7a).

These contracts drive the real generated index page inside jsdom: the page is
produced by core/index_builder.build_index into a temporary directory, and the
real templates/index/index.js is evaluated against it. No hand-written stub page
is accepted, because the thing under test is the artifact users actually open.

The expectations live in tests/js/index.test.js. Contracts that are still broken
are marked "xfail" there, STRICTLY: when one starts passing the JS suite fails,
so its marker has to be flipped to "pass". That mirrors the xfail(strict=True)
discipline used by the Python contracts.

The JS layer needs its own dependency (jsdom), installed in tests/js so it never
reaches the packaged EXE: packaging/MarkdownReader.spec collects only gui/assets,
templates and node_renderer. When that layer is not installed the module skips
with an explicit reason instead of failing.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.index_builder import build_index  # noqa: E402

JS_DIR = ROOT / "tests" / "js"
INDEX_JS = ROOT / "templates" / "index" / "index.js"

# Locked counts. They make a vanished or renamed contract a failure instead of a
# silent reduction of coverage.
EXPECTED_PASS = 1
EXPECTED_XFAIL = 2
EXPECTED_CONTRACTS = 3

# The fixture mirrors what a batch conversion hands the builder: one document in
# the output root, one folder with two documents so a search can single one out,
# and a second folder that must not match.
DOCUMENTS = [
    {"filename": "根文档.md", "title": "根文档"},
    {"filename": "甲组/一号.md", "title": "甲组一号"},
    {"filename": "甲组/二号.md", "title": "甲组二号"},
    {"filename": "乙组/乙文档.md", "title": "乙文档"},
]


def _js_harness_reason() -> str:
    """Return "" when the jsdom layer can run, otherwise a skip reason."""
    if shutil.which("node") is None:
        return "Node.js is not on PATH, so the index contracts cannot run."
    if not (JS_DIR / "index.test.js").is_file():
        return "tests/js/index.test.js is missing."
    if not (JS_DIR / "node_modules" / "jsdom").is_dir():
        return "jsdom is not installed; run: cd tests/js && npm ci"
    return ""


pytestmark = pytest.mark.skipif(
    bool(_js_harness_reason()), reason=_js_harness_reason() or "jsdom layer unavailable"
)


@pytest.fixture(scope="module")
def index_page(tmp_path_factory) -> dict:
    """Build a real index page once for the whole module."""
    root = tmp_path_factory.mktemp("index")
    generated = Path(build_index(str(root / "output"), DOCUMENTS, collection_name="契约索引"))

    # jsdom parses the page through a loopback URL while keeping the real Windows
    # path in location.pathname, which is the path the page copies from. The path
    # is percent-encoded, exactly as a file URL would be, because the page decodes
    # it again with decodeURIComponent.
    url = "http://localhost/" + quote(generated.as_posix().lstrip("/"), safe="/:")

    return {"path": generated, "url": url}


def test_index_state_contracts(index_page: dict):
    """Run the jsdom contract suite and enforce its reported outcome."""
    environment = dict(os.environ)
    environment.update(
        {
            "MR_INDEX_HTML": str(index_page["path"]),
            "MR_INDEX_JS": str(INDEX_JS),
            "MR_INDEX_URL": index_page["url"],
        }
    )
    completed = subprocess.run(
        ["node", "--test", "index.test.js"],
        cwd=str(JS_DIR),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (completed.stdout or "") + (completed.stderr or "")

    # The runner emits one synchronous line per contract; count them here rather
    # than trusting a summary printed at process exit. A truncated or crashed run
    # then shows up as a missing record instead of a smaller green suite. The
    # pattern is deliberately not anchored to the start of a line: the Node test
    # runner may prefix forwarded output.
    statuses = re.findall(r"CONTRACT (pass|xfail|xpass|fail) (.*)", output)
    assert len(statuses) == EXPECTED_CONTRACTS, (
        "expected " + str(EXPECTED_CONTRACTS) + " contract records but saw "
        + str(len(statuses)) + ":\n" + output
    )

    counts = Counter(status for status, _name in statuses)
    print("INDEX_CONTRACTS " + json.dumps({
        name: counts[name] for name in ("pass", "xfail", "xpass", "fail")
    }))
    print("INDEX_CONTRACT_RECORDS " + str(len(statuses)) + " of " + str(EXPECTED_CONTRACTS))
    assert counts["xpass"] == 0, (
        "a contract marked xfail now holds: flip its marker to \"pass\" in "
        "tests/js/index.test.js:\n" + output
    )
    assert counts["fail"] == 0, "a contract marked pass failed:\n" + output
    assert counts["pass"] == EXPECTED_PASS, output
    assert counts["xfail"] == EXPECTED_XFAIL, output
    assert completed.returncode == 0, output

