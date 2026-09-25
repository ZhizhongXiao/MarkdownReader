"""Materialise the assembled viewer script for the jsdom layer.

Phase 6B split the viewer into the modules listed in `viewer/js/manifest.json`.
The jsdom harness still takes ONE file path (`MR_VIEWER_JS`), so the tests hand it
the **assembled payload** produced by `core/viewer_assets.py` -- the same script
the delivered document inlines. That keeps the harness from drifting away from
what ships, and keeps the manifest the single declaration of the load order.

Test-only helper; jsdom never reaches the packaged EXE.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.viewer_assets import shared_viewer_js_text  # noqa: E402


def write_viewer_payload(directory: Path) -> Path:
    """Write the assembled viewer script into `directory` and return its path."""
    target = Path(directory) / "viewer.assembled.js"
    target.write_text(shared_viewer_js_text(), encoding="utf-8", newline="\n")
    return target
