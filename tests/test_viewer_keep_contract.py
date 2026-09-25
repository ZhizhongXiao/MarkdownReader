"""Phase 6A: the Viewer KEEP surface, frozen before anything moves.

Phase 6 reorganises the reader's assets and splits its script. Everything listed
here is a contract with the **generated document**: a reader's saved fold state,
their reading position, the print stylesheet and the viewer's own wiring all
depend on these names. The lists are explicit on purpose -- when a name vanishes
this module fails, instead of the failure appearing later in somebody's browser.

`docs/VIEWER_CONTRACT.md` explains why each group is a contract.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import viewer_assets  # noqa: E402

DOM_IDS = (
    "toolbar",
    "btn-expand-all-content",
    "btn-collapse-all-content",
    "btn-auto-numbering",
    "btn-dark-mode",
    "btn-print",
    "toc-sidebar",
    "btn-toggle-toc-panel",
    "toc-body",
    "toc-resizer",
    "content-area",
    "markdown-body",
    "back-to-top-btn",
)

# Document-scoped keys carry the document identity; reader-scoped keys are shared
# by every document. The legacy key is read-only and only seeds documents that
# have no v2 state yet.
STORAGE_KEYS = (
    "markdownreader-doc-state-v2:",
    "markdownreader-scroll-",
    "markdownreader-toc-collapsed-v2",
    "markdownreader-toc-panel-collapsed",
    "markdownreader-theme",
    "markdownreader-autonumbering",
    "markdownreader-toc-width",
    "markdownreader-expandlevel",
)

SELECTORS = (
    ".toc-row",
    ".toc-toggle",
    ".toc-link",
    ".is-collapsed",
    ".is-hidden-by-collapse",
    ".is-hidden-by-content-fold",
    ".heading-toggle",
    ".code-block-wrapper",
    ".copy-btn",
    ".viewer-container",
)

ATTRIBUTES = ("data-theme", "data-auto-numbering", "data-id", "data-level", "--sidebar-width")


def test_every_toolbar_and_layout_id_is_still_there():
    shell = viewer_assets.viewer_shell_text()
    missing = [name for name in DOM_IDS if f'id="{name}"' not in shell]

    assert shell.strip(), "viewer 外壳缺失"
    assert missing == [], missing


def test_every_stored_key_is_still_written_under_the_same_name():
    script = viewer_assets.shared_viewer_js_text()
    missing = [key for key in STORAGE_KEYS if key not in script]

    assert missing == [], missing


def test_the_class_and_attribute_hooks_survive():
    """脚本、布局样式与主题链合起来必须仍然提供这些钩子。"""
    surface = "".join(
        (
            viewer_assets.shared_viewer_js_text(),
            viewer_assets.viewer_layout_css_text(),
            viewer_assets.theme_css_chain("modern"),
        )
    )
    missing = [name for name in SELECTORS + ATTRIBUTES if name not in surface]

    assert missing == [], missing
