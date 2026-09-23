"""Body alignment contract for the reader templates.

Justified CJK text has no word spaces to stretch, so the browser widens the gaps
between characters: that is what a reviewer saw in a paragraph mixing Chinese,
file names and a URL. The templates must stay left-aligned, and an over-long
token must be allowed to wrap instead of being clipped by the content area.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
ALIGNMENT_FILES = (
    "default/viewer.css",
    "Modern/theme.css",
    "Office/theme.css",
    "Vscode/theme.css",
)


def test_no_body_text_is_justified():
    for relative in ALIGNMENT_FILES:
        text = (TEMPLATES / relative).read_text(encoding="utf-8")
        offenders = [
            line.strip()
            for line in text.splitlines()
            if "text-align" in line and "justify" in line
        ]
        assert offenders == [], (relative, offenders)

    shared = (TEMPLATES / "default" / "viewer.css").read_text(encoding="utf-8")
    assert "text-align:left" in shared


def test_an_over_long_token_may_wrap_in_the_content_area():
    shared = (TEMPLATES / "default" / "viewer.css").read_text(encoding="utf-8")

    # The content area clips on overflow, so without this rule a long URL or file
    # name would be cut off instead of wrapping onto the next line.
    assert "overflow-x:hidden" in shared
    assert "overflow-wrap:anywhere" in shared


def test_the_modern_print_frame_follows_the_text():
    """The tint belongs to the text column, never to the paper.

    The canvas stays white, and the column carries the theme tint plus two guide
    borders. The frame is drawn with borders on purpose: a border prints even when
    background graphics are switched off, so only the tint depends on that switch.
    """
    modern = (TEMPLATES / "Modern" / "theme.css").read_text(encoding="utf-8")
    print_block = modern.split("@media print", 1)[1]

    assert "background: var(--color-bg) !important" in print_block
    assert "border-left: 2px solid var(--modern-guide-border) !important" in print_block
    assert "border-right: 2px solid var(--modern-guide-border) !important" in print_block

    shared = (TEMPLATES / "print.css").read_text(encoding="utf-8")
    assert "html{background:#fff!important}" in shared
