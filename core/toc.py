"""TOC (Table of Contents) generator.

Builds the navigation sidebar HTML from the heading list supplied by the
Node renderer. Heading text is the TOC-safe inline HTML Node already rendered;
this module only splits the leading number and assembles the DOM.

v5.1 — Flat TOC with CSS Grid layout, number splitting, CSS triangles.
"""

import re


# ─────────────────────────────────────────────────────────────────
# Phase 5.1 — Flat TOC generator
# ─────────────────────────────────────────────────────────────────

def _split_number_parts(text: str) -> tuple[str, str, str]:
    """Split heading number from title text for TOC display only.

    Returns:
        A tuple of (number, title, raw_prefix) where raw_prefix is the exact
        text consumed before the title. A heading without a leading number
        returns (empty, text, empty).
    """
    patterns = [
        r"^(\d+(?:[.．]\d+)+)(?:[.．、])?[\s　]+(.+)$",
        r"^(\d+(?:[.．]\d+)+)(?![.．\d])[\s　]*(\S.*)$",
        r"^(\d+(?:[.．]\d+)+(?:[.．、]))[\s　]*(\D.*)$",
        r"^(\d+(?:[.．]\d+)*(?:[.．、]))[\s　]*(\S.*)$",
        r"^(\d+)[\s　]+(.+)$",
        r"^([（(][一二三四五六七八九十百千万\d]+[）)])[\s　]*(\S.*)$",
        r"^([一二三四五六七八九十百千万]+[、.．])[\s　]*(\S.*)$",
        r"^(第[一二三四五六七八九十百千万\d]+[章节篇部分])[\s　]*(\S.*)$",
    ]
    for pattern in patterns:
        m = re.match(pattern, text)
        if m:
            return m.group(1), m.group(2).strip(), text[: m.start(2)]
    return "", text, ""


def _split_number(text: str) -> tuple[str, str]:
    """Backward-compatible wrapper around _split_number_parts."""
    number, title, _ = _split_number_parts(text)
    return number, title


def _has_children(headings: list[dict], index: int) -> bool:
    """Return True if heading at index has immediate children (level > current)."""
    if index + 1 >= len(headings):
        return False
    current_level = headings[index]["level"]
    next_level = headings[index + 1]["level"]
    return next_level > current_level


def generate_toc_html(headings: list[dict]) -> str:
    """Generate Flat TOC HTML with structured DOM rows.

    Each row:
      <div class="toc-row" data-id="..." data-level="N" data-has-children="true/false">
        <button class="toc-toggle">...</button>  (or <span class="toc-toggle-placeholder"></span>)
        <a class="toc-link" href="#...">
          <span class="toc-number">1.</span>
          <span class="toc-title">Title</span>
        </a>
      </div>
    """
    if not headings:
        return ""

    lines = []
    for i, h in enumerate(headings):
        level = h["level"]
        anchor = h["anchor"]
        raw_text = h["text"]
        toc_html = h["toc_inline_html"]
        number, _title, raw_prefix = _split_number_parts(raw_text)
        has_children = _has_children(headings, i)

        if raw_prefix and toc_html.startswith(raw_prefix):
            rendered_title = toc_html[len(raw_prefix):]
        else:
            rendered_title = toc_html
        if number:
            number_html = f'<span class="toc-number">{number}</span>'
        else:
            number_html = '<span class="toc-number"></span>'

        data_has = "true" if has_children else "false"

        if has_children:
            toggle_html = (
                '<button class="toc-toggle" type="button" aria-label="折叠目录">'
                '<span class="toc-toggle-icon"></span>'
                "</button>"
            )
        else:
            toggle_html = '<span class="toc-toggle-placeholder"></span>'

        row = (
            f'<div class="toc-row" data-id="{anchor}" '
            f'data-level="{level}" data-has-children="{data_has}" '
            f'style="--toc-level: {level}">'
            f"{toggle_html}"
            f'<a class="toc-link" href="#{anchor}">'
            f"{number_html}"
            f'<span class="toc-title">{rendered_title}</span>'
            f"</a>"
            f"</div>"
        )
        lines.append(row)

    return "\n".join(lines)
