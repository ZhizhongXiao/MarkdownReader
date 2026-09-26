"""External themes: user-authored CSS installed under the user assets directory.

An external theme is a directory carrying ``metadata.json`` and the CSS files it
declares. It is CSS-only on purpose (AGENTS section 14): no JavaScript, no custom
viewer DOM, no network. A generated document embeds the whole theme, so it has to
keep working offline and keep working after the theme is deleted from
MarkdownReader (Phase 7 acceptance 3).

The reference policy is the one the closure checker already applies to a finished
document (``tools/standalone_closure.py``): a ``url()`` target that is not ``data:``,
``about:`` or a fragment is an external subresource, and ``core`` may not import
``tools``, so the patterns exist in both places with a contract test asserting they
agree rather than drifting apart.
"""

import base64
import json
import logging
import os
import re
import shutil

from core import viewer_assets

_logger = logging.getLogger(__name__)


class ExternalThemeError(ValueError):
    """Raised when a theme directory cannot be used as an external theme."""


# The id is also the installed directory name and the value in the reader's
# localStorage, so it has to be a plain lowercase slug.
THEME_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,31}$")

# Same two patterns as tools/standalone_closure.py (locked by
# tests/test_external_theme_contract.py): the loader and the checker must agree on
# what counts as an external reference.
CSS_URL_PATTERN = re.compile(r"""url\(\s*(?P<quote>["']?)(?P<ref>[^"'()]+)(?P=quote)\s*\)""")
CSS_IMPORT_PATTERN = re.compile(r"""@import\s+(?P<quote>["'])(?P<ref>[^"']+)(?P=quote)""")
INLINE_PREFIXES = ("data:", "about:", "#")
REMOTE_PATTERN = re.compile(r"^(?:https?:)?//", re.IGNORECASE)

MAX_FILES = 16
MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 1024 * 1024

# Markup or script that would escape the <style> element the theme is embedded in,
# or that can run code from CSS.
FORBIDDEN_CSS = (
    ("@import", "@import"),
    ("</style", "</style"),
    ("<script", "<script"),
    ("javascript:", "javascript"),
    ("expression(", "expression"),
    ("behavior:", "behavior"),
    ("-moz-binding", "-moz-binding"),
)

MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
}


def _read_text(path: str) -> str:
    """Return a text file's content, or ``""`` when it is missing."""
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _check_id(theme_id: str) -> None:
    """Refuse malformed and reserved ids."""
    if not THEME_ID_PATTERN.match(theme_id):
        raise ExternalThemeError(
            f"主题 id 必须匹配 {THEME_ID_PATTERN.pattern}：{theme_id!r}"
        )
    reserved = set(viewer_assets.RESERVED_THEME_IDS)
    if theme_id in reserved:
        raise ExternalThemeError(
            f"主题 id 是保留名，不能用于外置主题：{theme_id}（保留：{', '.join(sorted(reserved))}）"
        )


def _resolve_local(css_dir: str, theme_root: str, target: str, label: str) -> str:
    """Resolve a local ``url()`` target inside the theme, or explain why not."""
    candidate = os.path.abspath(os.path.join(css_dir, target))
    inside = candidate == theme_root or candidate.startswith(theme_root + os.sep)
    if not inside:
        raise ExternalThemeError(f"{label} 的 url() 逃逸主题目录：{target}")
    if not os.path.isfile(candidate):
        raise ExternalThemeError(f"{label} 引用的本地资源不存在：{target}")
    return candidate


def _check_css(text: str, label: str, css_dir: str, theme_root: str) -> None:
    """Refuse CSS that could run code, break out of <style>, or reach the network."""
    lowered = text.lower()
    for needle, reason in FORBIDDEN_CSS:
        if needle in lowered:
            raise ExternalThemeError(f"{label} 含有被禁止的内容：{reason}")

    import_match = CSS_IMPORT_PATTERN.search(text)
    if import_match:
        raise ExternalThemeError(
            f"{label} 不得使用 @import（{import_match.group('ref')}）：外置主题必须离线自包含。"
        )

    for match in CSS_URL_PATTERN.finditer(text):
        target = match.group("ref").strip()
        if target.startswith(INLINE_PREFIXES):
            continue
        if REMOTE_PATTERN.match(target):
            raise ExternalThemeError(
                f"{label} 引用了远程资源（{target}）：外置主题必须离线自包含。"
            )
        _resolve_local(css_dir, theme_root, target, label)


def validate_theme_directory(directory: str) -> dict:
    """Validate a theme directory and return its metadata.

    Everything an external theme may not do is refused here, before the files are
    copied anywhere: a bad theme must fail at import with a reason, not at render
    time in someone's browser.
    """
    base = os.path.abspath(str(directory))
    if not os.path.isdir(base):
        raise ExternalThemeError(f"主题目录不存在：{base}")

    metadata_path = os.path.join(base, "metadata.json")
    if not os.path.isfile(metadata_path):
        raise ExternalThemeError(f"主题缺少 metadata.json：{base}")
    try:
        with open(metadata_path, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
    except Exception as error:
        raise ExternalThemeError(f"metadata.json 无法解析：{metadata_path}（{error}）") from error
    if not isinstance(metadata, dict):
        raise ExternalThemeError(f"metadata.json 根节点必须是对象：{metadata_path}")

    theme_id = str(metadata.get("id") or "")
    _check_id(theme_id)

    if not str(metadata.get("name") or "").strip():
        raise ExternalThemeError("metadata.json 缺少 name。")

    parent = metadata.get("extends")
    if parent is not None:
        if not isinstance(parent, str) or not viewer_assets.theme_source(parent):
            raise ExternalThemeError(f"父主题不存在：{parent}")

    declared = metadata.get("files")
    if not isinstance(declared, list) or not declared:
        raise ExternalThemeError("metadata.json 必须声明 files 列表（该主题提供的 CSS 文件）。")
    if len(declared) > MAX_FILES:
        raise ExternalThemeError(f"files 最多 {MAX_FILES} 个文件：{len(declared)}")

    total = 0
    for entry in declared:
        filename = str(entry)
        if not filename.lower().endswith(".css"):
            raise ExternalThemeError(f"files 只允许 CSS 文件：{filename}")
        if os.path.isabs(filename) or ".." in filename.replace("\\", "/").split("/"):
            raise ExternalThemeError(f"声明文件不得逃逸主题目录：{filename}")
        path = os.path.join(base, filename)
        if not os.path.isfile(path):
            raise ExternalThemeError(f"主题缺少声明的 CSS 文件：{filename}")
        size = os.path.getsize(path)
        if size > MAX_FILE_BYTES:
            raise ExternalThemeError(
                f"{filename} 超过单文件上限 {MAX_FILE_BYTES // 1024} KiB：{size} bytes"
            )
        total += size
        _check_css(_read_text(path), filename, os.path.dirname(path), base)

    if total > MAX_TOTAL_BYTES:
        raise ExternalThemeError(
            f"主题 CSS 总量超过上限 {MAX_TOTAL_BYTES // 1024} KiB：{total} bytes"
        )

    return metadata


def theme_root() -> str:
    """Return the directory external themes are installed in."""
    return viewer_assets.external_themes_root()


def import_theme(source: str, *, replace: bool = False) -> str:
    """Validate ``source`` and install it as an external theme, returning its id.

    The id comes from ``metadata.json``, not from the source directory name, so a user
    can export the template anywhere, edit it, and import the folder without renaming
    it first. Nothing is installed unless validation passed.
    """
    metadata = validate_theme_directory(source)
    theme_id = str(metadata["id"])
    base = os.path.abspath(str(source))
    root = os.path.abspath(theme_root())
    if base == root or base.startswith(root + os.sep):
        raise ExternalThemeError("源目录已经是安装目录（如需覆盖请用 replace=True 重新导入）。")

    target = os.path.join(root, theme_id)
    if os.path.isdir(target) and not replace:
        raise ExternalThemeError(f"主题“{theme_id}”已安装；如需覆盖请显式 replace=True。")

    os.makedirs(root, exist_ok=True)
    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(base, target)
    _logger.info("已安装外置主题：%s -> %s", base, target)
    return theme_id


def remove_theme(theme_id: str) -> None:
    """Delete an installed external theme. Packaged themes are never touched."""
    if viewer_assets.theme_source(theme_id) != viewer_assets.SOURCE_EXTERNAL:
        raise ExternalThemeError(f"未安装的外置主题：{theme_id}")
    root = os.path.abspath(theme_root())
    target = os.path.abspath(os.path.join(root, str(theme_id)))
    if os.path.dirname(target) != root:
        raise ExternalThemeError(f"主题 id 不合法：{theme_id}")
    shutil.rmtree(target)
    _logger.info("已删除外置主题：%s", target)


def export_template(destination: str) -> str:
    """Copy the packaged theme template into ``destination`` and return that path.

    The template is a real theme, so exporting it produces a folder that already
    imports cleanly: "edit it and import it back" needs no scaffolding (Phase 7
    acceptance 1 and 2).
    """
    template = viewer_assets.theme_template_root()
    if not os.path.isdir(template):
        raise ExternalThemeError(f"主题模板缺失：{template}")
    target = os.path.abspath(str(destination))
    if target == os.path.abspath(template):
        raise ExternalThemeError("导出目标不能是随包的主题模板目录。")
    if os.path.exists(target):
        raise ExternalThemeError(f"导出目标已存在：{target}")
    shutil.copytree(template, target)
    _logger.info("已导出主题模板：%s -> %s", template, target)
    return target


def inline_theme_css(theme_id: str) -> str:
    """Return a theme's CSS with its local ``url()`` assets embedded as data URIs.

    This is what makes a generated document independent of the installed theme: once
    the theme is deleted from MarkdownReader the document still renders (Phase 7
    acceptance 3).
    """
    directory = viewer_assets.theme_dir(theme_id)
    if not directory:
        raise ExternalThemeError(f"未安装主题：“{theme_id}”")
    root = os.path.abspath(directory)
    parts = []
    for filename in viewer_assets.theme_files(theme_id):
        path = os.path.join(root, filename)
        parts.append(_inline_assets(_read_text(path), os.path.dirname(path), root, filename))
    return "\n".join(parts)


def theme_bundle(selected: list[str] | None = None, *, default: str | None = None) -> list[dict]:
    """Return every theme a document carries: id, source and inline-ready CSS.

    Order is base, then the builtin themes, then the selected user themes. base holds
    the tokens; each selectable theme scopes its rules to its own id, so a later theme
    only wins for what it actually sets.

    A document whose default theme is an installed user theme carries it even when the
    selection forgot to mention it: the alternative is a document that opens in a theme
    it does not contain.
    """
    chosen = {str(item) for item in (selected or [])}
    default_id = str(default) if default else ""
    if default_id and viewer_assets.theme_source(default_id) == viewer_assets.SOURCE_EXTERNAL:
        if default_id not in chosen:
            _logger.warning("文档默认主题 %s 未在选中列表里，已自动补入本文档。", default_id)
            chosen.add(default_id)

    order = [viewer_assets.BASE_THEME_ID, *viewer_assets.builtin_theme_ids()]
    order.extend(viewer_assets.selectable_theme_ids(sorted(chosen)))

    payload = []
    for theme_id in dict.fromkeys(order):
        source = viewer_assets.theme_source(theme_id)
        css = (
            inline_theme_css(theme_id)
            if source == viewer_assets.SOURCE_EXTERNAL
            else viewer_assets.theme_css_text(theme_id)
        )
        payload.append({"id": theme_id, "source": source, "css": css})
    return payload


def _inline_assets(css: str, css_dir: str, theme_root: str, label: str) -> str:
    """Replace every allowed local ``url()`` target with a data URI."""

    def replace(match: re.Match) -> str:
        target = match.group("ref").strip()
        if target.startswith(INLINE_PREFIXES):
            return match.group(0)
        if REMOTE_PATTERN.match(target):
            raise ExternalThemeError(
                f"{label} 引用了远程资源（{target}）：外置主题必须离线自包含。"
            )
        path = _resolve_local(css_dir, theme_root, target, label)
        mime = MIME_TYPES.get(os.path.splitext(path)[1].lower())
        if not mime:
            raise ExternalThemeError(f"{label} 引用了不支持的资源类型：{target}")
        with open(path, "rb") as handle:
            payload = base64.b64encode(handle.read()).decode("ascii")
        return "url(data:" + mime + ";base64," + payload + ")"

    return CSS_URL_PATTERN.sub(replace, css)
