"""Reader asset layer: what a generated document is made of, and where from.

Phase 6A collected this knowledge into one module; Phase 6B moved the assets it
points at (and split the viewer script). Both assembly paths, the GUI dropdown and
the tests now read the layout through this one layer, which is why the move
touched paths here instead of in five modules.

Two boundaries are deliberate:

* `core/config.py` keeps its own job -- config.json, bundle paths, page
  placeholders -- and never imports this module, so there is no cycle. The
  dependency only ever points this way: `viewer_assets` -> `config`.
* The batch index page (`core/index_builder.py`) is a separate surface: its own
  shell, its own stylesheet, its own state model. It is not part of the reader
  asset layer.

Delivered documents are standalone files opened over ``file://``. That fixes one
runtime rule here: the viewer ships as **one classic script**, assembled from the
modules listed in ``viewer/js/manifest.json`` -- fragments of a single IIFE in file
order, joined with no separator so the payload stays byte-identical to the file
they replace. ``<script type="module">`` would be blocked by CORS on ``file://``,
and fetching module files at runtime would break the offline promise.

Terminology: a theme id is the canonical lowercase id from ``metadata.json``, which
is also its directory name under ``themes/builtin/``. The user-facing selector in
``config.json`` is that same id.
"""

import json
import logging
import os
from html import escape

from core.config import BUNDLE_ROOT, normalize_template_name

_logger = logging.getLogger(__name__)

# Phase 6B moved the reader's assets out of `templates/` (which now holds only the
# batch index page): the shell and its styles/script live under `viewer/`, and the
# themes under `themes/builtin/<id>/`. This module is the only place that knows it.
_VIEWER_ROOT = os.path.join(BUNDLE_ROOT, "viewer")
_THEMES_ROOT = os.path.join(BUNDLE_ROOT, "themes", "builtin")
_VIEWER_SHELL = os.path.join(_VIEWER_ROOT, "viewer.html")
_VIEWER_LAYOUT_CSS = os.path.join(_VIEWER_ROOT, "css", "layout.css")
_VIEWER_PRINT_CSS = os.path.join(_VIEWER_ROOT, "css", "print.css")
_VIEWER_JS_MANIFEST = os.path.join(_VIEWER_ROOT, "js", "manifest.json")
# The viewer used to be one file with a leading UTF-8 BOM, and that byte reached
# the delivered document. The modules carry no BOM, so the loader puts it back and
# the assembled payload stays byte-identical to the pre-6B file.
_VIEWER_JS_BOM = "\ufeff"


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
    path = os.path.join(_THEMES_ROOT, str(theme_id), "metadata.json")
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
    if os.path.isdir(_THEMES_ROOT):
        for entry in os.listdir(_THEMES_ROOT):
            if not os.path.isdir(os.path.join(_THEMES_ROOT, entry)):
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


def builtin_theme_ids() -> list[str]:
    """Return the selectable builtin theme ids, in bundle order.

    Phase 6C ships every builtin theme inside each document, so this list is both
    the order the bundle follows and the set the switcher offers. External themes
    (Phase 7) get their own channel and never join it.
    """
    return theme_ids()


def builtin_themes() -> list[tuple[str, str]]:
    """Return ``(theme_id, display name)`` for every selectable builtin theme.

    The display name comes from ``metadata.json`` ("Modern", "Office", "VS Code"),
    which is what the switcher shows; the delivered document never needs the
    directory layout to know it.
    """
    pairs: list[tuple[str, str]] = []
    for theme_id in builtin_theme_ids():
        name = str(theme_metadata(theme_id).get("name") or theme_id)
        pairs.append((theme_id, name))
    return pairs


def normalize_theme_id(theme_id: str | None) -> str:
    """Normalize a theme selector (aliases included) to its canonical id."""
    return normalize_template_name(theme_id)


def theme_menu_markup() -> str:
    """Return the theme menu markup for the shell's ``{{THEME_MENU}}`` placeholder.

    The menu ships inside the document instead of being built by the viewer script:
    the options and their names are registry facts, and the page must be correct
    before any script runs (Phase 6C).
    """
    options = "".join(
        '<button type="button" class="theme-option" data-theme-id="'
        + escape(theme_id, quote=True)
        + '">'
        + escape(name)
        + "</button>"
        for theme_id, name in builtin_themes()
    )
    return '<div class="theme-menu" id="theme-menu" hidden>' + options + "</div>"


def validate_theme(theme_id: str) -> str:
    """Return the normalized theme id, raising ``ValueError`` when it is unusable.

    "Usable" means it exists, its inheritance resolves, and it is **selectable**:
    the base theme only carries fallback tokens, so a document whose default were
    ``base`` would render with no component rules at all. The assembly paths call
    this before they read anything else -- an unknown theme, a circular inheritance
    or a missing parent must fail exactly as it did while the page shell was still
    resolved through the theme chain.
    """
    normalized = normalize_theme_id(theme_id)
    resolve_theme_chain(normalized)
    selectable = builtin_theme_ids()
    if normalized not in selectable:
        raise ValueError(
            f"“{normalized}”不是可选主题；可选：" + ", ".join(selectable)
        )
    return normalized


# ================================================================
# Chain resolution
# ================================================================


def resolve_theme_chain(theme_id: str) -> list[str]:
    """Build the inheritance chain, base first.

    For a theme extending ``default`` that is ``["default", "<theme>"]``. Raises
    ``ValueError`` when the theme is missing, circular, or extends a missing one.
    """
    theme_id = normalize_theme_id(theme_id)

    if not os.path.isdir(os.path.join(_THEMES_ROOT, theme_id)):
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
        if not os.path.isdir(os.path.join(_THEMES_ROOT, parent)):
            raise ValueError(f"模板“{current}”继承“{parent}”，但未找到父模板“{parent}”。")
        chain.insert(0, parent)
        seen.add(parent)
        current = parent

    return chain


def resolve_theme_file(theme_id: str, filename: str) -> str | None:
    """Find a file in a theme's chain, searching from the theme up to its base.

    Only ``theme.css`` is per-theme now: the shell, the layout stylesheet, the
    viewer script and the print sheet are shared assets (see the getters below).
    """
    for name in reversed(resolve_theme_chain(theme_id)):
        path = os.path.join(_THEMES_ROOT, name, filename)
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
        text = _read_text(os.path.join(_THEMES_ROOT, name, "theme.css"))
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


def theme_css_text(theme_id: str) -> str:
    """Return one theme's own ``theme.css`` (no chain), raising when it is missing.

    Phase 6C inlines every builtin theme separately, so the bundle goes through
    here rather than through ``theme_css_chain()``: a missing file is a broken
    package (the spec names these files as required) and must not be downgraded to
    "no styles for that theme".
    """
    path = os.path.join(_THEMES_ROOT, str(theme_id), "theme.css")
    text = _read_text(path)
    if not text:
        raise ValueError(f"主题缺少 theme.css：{path}")
    return text


# The base theme carries the global fallback tokens and is never selectable; every
# selectable theme inherits from it.
BASE_THEME_ID = "base"


def builtin_theme_css_text() -> str:
    """Return base plus every builtin theme, each exactly once, in a fixed order.

    Order is base, modern, office, vscode. ``theme_css_chain()`` stays available for
    a single-theme view (diagnostics, external themes), but the delivered document
    comes from here since Phase 6C: the reader carries all of them and switches at
    runtime, so "which theme is in the page" is no longer a per-document decision.
    """
    order = (BASE_THEME_ID, *builtin_theme_ids())
    return "\n".join(theme_css_text(theme_id) for theme_id in order)


# ================================================================
# Shared reader assets
# ================================================================


def viewer_shell_text() -> str:
    """Return the page shell every theme shares, or ``""``.

    Phase 6B made the shell a shared asset: it used to be resolved through the
    theme chain (only the base template carried one), which no longer describes
    the layout.
    """
    return _read_text(_VIEWER_SHELL)


def viewer_layout_css_text() -> str:
    """Return the shared layout/component stylesheet, or ``""``.

    Colors and sizes arrive as CSS variables from the theme chain, so this file is
    layout and components only.
    """
    return _read_text(_VIEWER_LAYOUT_CSS)


def viewer_js_modules() -> list[str]:
    """Return the viewer script's module names in load order.

    ``viewer/js/manifest.json`` is the only declaration of that order; the
    assembler and the tests both go through this function, so a reordered manifest
    cannot be missed by one of them.
    """
    raw = _read_text(_VIEWER_JS_MANIFEST)
    if not raw.strip():
        raise ValueError(f"缺少 viewer 脚本清单：{_VIEWER_JS_MANIFEST}")
    try:
        manifest = json.loads(raw)
    except ValueError as error:
        raise ValueError(f"viewer 脚本清单无法解析：{_VIEWER_JS_MANIFEST}（{error}）") from error
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError(f"viewer 脚本清单缺少 files 列表：{_VIEWER_JS_MANIFEST}")
    return [str(name) for name in files]


def shared_viewer_js_text() -> str:
    """Return the viewer script every document inlines, assembled from the manifest.

    The modules are fragments of **one** IIFE in file order, so they are joined with
    no separator: the result equals the pre-6B ``templates/viewer.js`` byte for byte
    (locked by ``tests/test_viewer_assets_contract.py``). A module that does not end
    with a newline would glue onto the next one, so that is refused rather than
    patched.
    """
    chunks: list[str] = []
    for name in viewer_js_modules():
        path = os.path.join(_VIEWER_ROOT, "js", name)
        chunk = _read_text(path)
        if not chunk:
            raise ValueError(f"viewer 脚本模块缺失或为空：{path}")
        if not chunk.endswith("\n"):
            raise ValueError(f"viewer 脚本模块必须以换行结尾：{path}")
        chunks.append(chunk)
    return _VIEWER_JS_BOM + "".join(chunks)


def shared_print_css_text() -> str:
    """Return the print stylesheet that every document inlines, or ``""``."""
    return _read_text(_VIEWER_PRINT_CSS)

