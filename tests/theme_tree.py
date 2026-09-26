"""Fixture helper: a builtin theme tree with one required file removed.

Phase 6C made the builtin theme bundle a required part of every delivered document
(每份 HTML 固定携带 base + modern + office + vscode). A missing ``theme.css`` is
therefore a broken package: assembly must fail rather than ship a document without
that theme's variables. Two layers lock that behaviour -- the assembly contract in
`test_theme_bundle_contract.py` and the conversion boundary in
`test_converter_v2_integration.py` -- and both need the same broken tree, so it
lives here instead of being copy-pasted.

The real themes are copied rather than stubbed: the point is that the *shipped*
registry loses a file, and a hand-written metadata-only tree could disagree with it.
"""

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
THEMES_ROOT = REPO_ROOT / "themes" / "builtin"


def broken_theme_tree(tmp_path: Path, missing: str = "office") -> Path:
    """Return a copy of ``themes/builtin`` without ``<missing>/theme.css``.

    Args:
        tmp_path: Destination root (a pytest ``tmp_path``).
        missing: Theme directory whose required ``theme.css`` is removed.
    """
    target = tmp_path / "builtin"
    shutil.copytree(THEMES_ROOT, target)
    removed = target / missing / "theme.css"
    assert removed.is_file(), f"fixture precondition: {missing}/theme.css must exist"
    removed.unlink()
    return target
