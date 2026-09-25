"""Reader asset layer: what a generated document is made of, and where from.

Phase 6A. The knowledge "which files make up a reader document" used to live in
several places at once: `core/config.py` resolved the template chain, each of the
two assembly paths read the files itself, and the GUI listed the template
directory to build its dropdown. This module is that knowledge's single home, so
the later Phase 6 steps (moving the assets, splitting the viewer, embedding every
builtin theme) change one file instead of five.

Two boundaries are deliberate:

* `core/config.py` keeps its own job -- config.json, bundle paths, page
  placeholders -- and never imports this module, so there is no cycle. The
  dependency only ever points this way: `viewer_assets` -> `config`.
* The batch index page (`core/index_builder.py`) is a separate surface: its own
  shell, its own stylesheet, its own state model. It is not part of the reader
  asset layer.

Delivered documents are standalone files opened over ``file://``. That fixes one
runtime rule here: the viewer ships as **one classic script**. Source-level
modules (Phase 6B) are concatenated at assembly time; ``<script type="module">``
would be blocked by CORS on ``file://``, and fetching module files at runtime
would break the offline promise.

Terminology: a *template* is a user-facing selector (today the directory name,
for example ``Modern``), while a *theme id* is the canonical lowercase id from
its ``metadata.json`` (``modern``). They differ in case today and will be unified
when Phase 6B moves the assets under ``themes/builtin/<id>/``.
"""

import json
import logging
import os

from core.config import TEMPLATES_DIR, normalize_template_name

_logger = logging.getLogger(__name__)

# Phase 6B moves these under viewer/ and themes/builtin/<id>/. Until then they are
# still the template directories, and this module is the only place that knows it.
_ASSET_ROOT = TEMPLATES_DIR
_SHARED_VIEWER_JS = os.path.join(_ASSET_ROOT, "viewer.js")
_SHARED_PRINT_CSS = os.path.join(_ASSET_ROOT, "print.css")


def _read_text(path: str | None) -> str:
    """Return the file text, or an empty string when it is missing."""
    if not path or not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


# ================================================================
# Theme registry
# ================================================================


def theme_metadata(theme_id: str) -> dict:
    """Return a theme's ``metadata.json``, or ``{}`` when it is unreadable."""
    path = os.path.join(_ASSET_ROOT, str(theme_id), "metadata.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as error:
            _logger.warning("解析主题元数据失败：%s；原因：%s", path, error)
    return {}


def theme_ids(*, include_hidden: bool = False) -> list[str]:
    """Return the selectable theme names, sorted.

    A directory counts as a theme when it carries a ``metadata.json``; the index
    page therefore never appears here (it has no metadata), and the base theme
    stays out unless ``include_hidden`` is asked for. The GUI used to open the
    template directory itself to answer this question.
    """
    names = []
    if os.path.isdir(_ASSET_ROOT):
        for entry in os.listdir(_ASSET_ROOT):
            if not os.path.isdir(os.path.join(_ASSET_ROOT, entry)):
                continue
            metadata = theme_metadata(entry)
            if not metadata:
                continue
            if include_hidden or not metadata.get("hidden", False):
                names.append(entry)
    return sorted(names)


def theme_body_class(theme_id: str) -> str:
    """Return the stable CSS class of a theme.

    Single implementation for the v1 converter and the v2 assembler; the class
    *name* stays an implementation detail of this layer.
    """
    safe_name = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(theme_id)).strip("-")
    return f"theme-{safe_name or 'default'}"


def normalize_theme_id(theme_id: str | None) -> str:
    """Normalize a theme selector (aliases included) to its canonical id."""
    return normalize_template_name(theme_id)


# ================================================================
# Chain resolution
# ================================================================


def resolve_theme_chain(theme_id: str) -> list[str]:
    """Build the inheritance chain, base first.

    For a theme extending ``default`` that is ``["default", "<theme>"]``. Raises
    ``ValueError`` when the theme is missing, circular, or extends a missing one.
    """
    theme_id = normalize_theme_id(theme_id)

    if not os.path.isdir(os.path.join(_ASSET_ROOT, theme_id)):
        raise ValueError(f"未找到模板：“{theme_id}”")

    chain = [theme_id]
    seen = {theme_id}
    current = theme_id

    while True:
        parent = theme_metadata(current).get("extends")
        if parent is None:
            break
        if parent in seen:
            raise ValueError(f"检测到模板循环继承：{' -> '.join(chain + [parent])}")
        if not os.path.isdir(os.path.join(_ASSET_ROOT, parent)):
            raise ValueError(f"模板“{current}”继承“{parent}”，但未找到父模板“{parent}”。")
        chain.insert(0, parent)
        seen.add(parent)
        current = parent

    return chain


def resolve_theme_file(theme_id: str, filename: str) -> str | None:
    """Find a file in the chain, searching from the theme up to its base."""
    for name in reversed(resolve_theme_chain(theme_id)):
        path = os.path.join(_ASSET_ROOT, name, filename)
        if os.path.isfile(path):
            return path
    return None


def theme_css_chain(theme_id: str) -> str:
    """Read and concatenate ``theme.css`` along the chain, base first.

    Children come later so their variables win the cascade. Raises ``ValueError``
    when the chain carries no ``theme.css`` at all.
    """
    chain = resolve_theme_chain(theme_id)
    parts: list[str] = []
    for name in chain:
        text = _read_text(os.path.join(_ASSET_ROOT, name, "theme.css"))
        if text:
            parts.append(text)
            _logger.debug("已加载主题样式：%s/theme.css", name)
        else:
            _logger.debug("主题 %s 没有 theme.css，已跳过。", name)
    if not parts:
        raise ValueError(
            f"模板“{theme_id}”的继承链中没有 theme.css。继承链：{' -> '.join(chain)}"
        )
    return "\n".join(parts)


# ================================================================
# Shared reader assets
# ================================================================


def viewer_shell_text(theme_id: str) -> str:
    """Return the page shell (``viewer.html``) for a theme, or ``""``."""
    return _read_text(resolve_theme_file(theme_id, "viewer.html"))


def viewer_layout_css_text(theme_id: str) -> str:
    """Return the layout/component stylesheet (``viewer.css``), or ``""``.

    Colors and sizes arrive as CSS variables from the theme chain, so this file
    is layout and components only.
    """
    return _read_text(resolve_theme_file(theme_id, "viewer.css"))


def shared_viewer_js_text() -> str:
    """Return the viewer script that every document inlines, or ``""``.

    One classic script today; Phase 6B concatenates the source modules in
    ``manifest`` order here, which keeps the delivered document unchanged in
    shape.
    """
    return _read_text(_SHARED_VIEWER_JS)


def shared_print_css_text() -> str:
    """Return the print stylesheet that every document inlines, or ``""``."""
    return _read_text(_SHARED_PRINT_CSS)

