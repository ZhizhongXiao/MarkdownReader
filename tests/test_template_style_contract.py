"""Body alignment contract for the reader assets.

Justified CJK text has no word spaces to stretch, so the browser widens the gaps
between characters: that is what a reviewer saw in a paragraph mixing Chinese,
file names and a URL. The themes must stay left-aligned, and an over-long token
must be allowed to wrap instead of being clipped by the content area.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "viewer"
THEMES = ROOT / "themes" / "builtin"
ALIGNMENT_FILES = (
    VIEWER / "css" / "layout.css",
    THEMES / "modern" / "theme.css",
    THEMES / "office" / "theme.css",
    THEMES / "vscode" / "theme.css",
)


def test_no_body_text_is_justified():
    for path in ALIGNMENT_FILES:
        text = path.read_text(encoding="utf-8")
        offenders = [
            line.strip() for line in text.splitlines() if "text-align" in line and "justify" in line
        ]
        assert offenders == [], (path.as_posix(), offenders)

    shared = (VIEWER / "css" / "layout.css").read_text(encoding="utf-8")
    assert "text-align:left" in shared


def test_an_over_long_token_may_wrap_in_the_content_area():
    shared = (VIEWER / "css" / "layout.css").read_text(encoding="utf-8")

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
    modern = (THEMES / "modern" / "theme.css").read_text(encoding="utf-8")
    print_block = modern.split("@media print", 1)[1]

    assert "background: var(--color-bg) !important" in print_block
    assert "border-left: 2px solid var(--modern-guide-border) !important" in print_block
    assert "border-right: 2px solid var(--modern-guide-border) !important" in print_block
    assert "body.theme-modern .content-area" not in print_block, (
        "the print block must not add page padding: that narrows the text beyond the "
        "browser's own page margins, which is what a reviewer saw as changed margins"
    )

    shared = (VIEWER / "css" / "print.css").read_text(encoding="utf-8")
    assert "html{background:#fff!important}" in shared
