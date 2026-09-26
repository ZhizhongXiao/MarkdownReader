"""External themes: user-authored CSS installed under the user assets directory.

An external theme is a directory carrying ``metadata.json`` and the CSS files it
declares. It is CSS-only on purpose (AGENTS section 14): no JavaScript, no custom
viewer DOM, no network. A generated document embeds the whole theme, so it has to keep
working offline and keep working after the theme is deleted from MarkdownReader
(Phase 7 acceptance 3).

Two rules shape this module:

* **Validation happens at import time and again at every read.** The installed
directory is a persistent user asset that later phases will let people open and edit,
so "it was valid when it was installed" is not a reason to trust it afterwards.
* **One scanner, three consumers.** ``core.css_audit`` owns the CSS analysis used by
  this module, by the asset inliner and by the standalone closure checker: there is no
  second URL parser behind the scenes. The theme *policy* (scope, at-rules, data URIs)
  lives there as well, but the checker deliberately shares only the scanner -- ordinary
  author CSS and the CSS-only theme format are different trust boundaries.
"""

import base64
import json
import logging
import os
import re
import shutil

from core import css_audit, viewer_assets

_logger = logging.getLogger(__name__)


class ExternalThemeError(ValueError):
    """Raised when a theme directory cannot be used as an external theme."""


# The id is also the installed directory name and the value in the reader's
# localStorage, so it has to be a plain lowercase slug.
THEME_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,31}$")

# An external theme may only extend the global token layer. Extending a builtin
# *selectable* theme would be semantically false after Phase 6C: those themes scope
# their rules to their own id, so the parent's CSS would not apply while another theme
# is active. Selector rebasing or token inheritance would have to be designed first.
ALLOWED_PARENTS = ("base",)

MAX_FILES = 16
# Budgets are for the payload that ends up inside the document, not for the directory:
# declared CSS bytes plus, for every asset reference actually expanded, its base64
# payload and the `data:<mime>;base64,` prefix.
MAX_CSS_BYTES = 512 * 1024
MAX_ASSET_BYTES = 2 * 1024 * 1024
MAX_PAYLOAD_BYTES = 8 * 1024 * 1024

# Extension to MIME, deliberately a subset of css_audit.ALLOWED_DATA_MIME: an SVG is
# markup and would need its own content audit, so Phase 7 refuses it entirely.
ASSET_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
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
        raise ExternalThemeError(f"主题 id 必须匹配 {THEME_ID_PATTERN.pattern}：{theme_id!r}")
    reserved = set(viewer_assets.RESERVED_THEME_IDS)
    if theme_id in reserved:
        raise ExternalThemeError(
            f"主题 id 是保留名，不能用于外置主题：{theme_id}（保留：{', '.join(sorted(reserved))}）"
        )


def _contained(candidate: str, root: str) -> bool:
    """Return True when ``candidate`` really lives inside ``root``.

    Both sides are resolved first: a symlink or junction inside the theme directory
    points somewhere else on disk while looking contained as a string, and only the
    real path can tell. Comparison is case-insensitive on Windows.
    """
    real_candidate = os.path.normcase(os.path.realpath(candidate))
    real_root = os.path.normcase(os.path.realpath(root))
    return real_candidate == real_root or real_candidate.startswith(real_root + os.sep)


def _resolve_local(css_dir: str, theme_root: str, target: str, label: str) -> str:
    """Resolve a local reference to a real file inside the theme, or refuse."""
    candidate = os.path.join(css_dir, target)
    if not _contained(candidate, theme_root):
        raise ExternalThemeError(f"{label} 的 url() 逃逸主题目录：{target}")
    if not os.path.isfile(candidate):
        raise ExternalThemeError(f"{label} 引用的本地资源不存在：{target}")
    return os.path.realpath(candidate)


def _asset_payload(css_dir: str, theme_root: str, target: str, label: str) -> tuple[str, int]:
    """Return ``(data URI, payload bytes)`` for one local asset reference."""
    path = _resolve_local(css_dir, theme_root, target, label)
    mime = ASSET_MIME_TYPES.get(os.path.splitext(path)[1].lower())
    if not mime:
        raise ExternalThemeError(f"{label} 引用了不支持的资源类型：{target}")
    size = os.path.getsize(path)
    if size > MAX_ASSET_BYTES:
        raise ExternalThemeError(
            f"{label} 引用的资源超过单文件上限 {MAX_ASSET_BYTES // 1024} KiB：{target}"
        )
    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    prefix = "data:" + mime + ";base64,"
    return prefix + encoded, len(prefix) + len(encoded)


def validate_theme_directory(directory: str) -> dict:
    """Validate a theme directory and return its metadata.

    Every rule an external theme must obey is checked here, and the same function runs
    at import time and again on every read, because an installed theme is a user asset
    that may be edited afterwards.
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
        if not isinstance(parent, str) or parent not in ALLOWED_PARENTS:
            raise ExternalThemeError(
                "外置主题的 extends 只允许 "
                + " / ".join(ALLOWED_PARENTS)
                + " 或 null："
                + str(parent)
            )
        if not viewer_assets.theme_source(parent):
            raise ExternalThemeError(f"父主题不存在：{parent}")

    declared = metadata.get("files")
    if not isinstance(declared, list) or not declared:
        raise ExternalThemeError("metadata.json 必须声明 files 列表（该主题提供的 CSS 文件）。")
    if len(declared) > MAX_FILES:
        raise ExternalThemeError(f"files 最多 {MAX_FILES} 个文件：{len(declared)}")

    css_total = 0
    payload_total = 0
    for entry in declared:
        filename = str(entry)
        if not filename.lower().endswith(".css"):
            raise ExternalThemeError(f"files 只允许 CSS 文件：{filename}")
        if os.path.isabs(filename) or ".." in filename.replace("\\", "/").split("/"):
            raise ExternalThemeError(f"声明文件不得逃逸主题目录：{filename}")
        path = os.path.join(base, filename)
        if not _contained(path, base):
            raise ExternalThemeError(f"声明文件的真实路径逃逸主题目录：{filename}")
        text = _read_text(path)
        if not text:
            raise ExternalThemeError(f"主题缺少声明的 CSS 文件：{filename}")

        css_bytes = len(text.encode("utf-8"))
        css_total += css_bytes
        # The payload budget is what ends up in the document, so the CSS counts too;
        # MAX_CSS_BYTES stays as the stricter cap on CSS alone.
        payload_total += css_bytes
        if css_total > MAX_CSS_BYTES:
            raise ExternalThemeError(f"主题 CSS 总量超过上限 {MAX_CSS_BYTES // 1024} KiB")

        try:
            references = css_audit.check_theme_references(text, theme_id)
        except css_audit.CssAuditError as error:
            raise ExternalThemeError(f"{filename}：{error}") from error

        for reference in references:
            if css_audit.reference_kind(reference.target) != "local":
                continue
            _, payload = _asset_payload(
                os.path.dirname(path), base, reference.target, filename
            )
            payload_total += payload
            if payload_total > MAX_PAYLOAD_BYTES:
                raise ExternalThemeError(
                    "内嵌载荷超过上限 " + str(MAX_PAYLOAD_BYTES // 1024 // 1024) + " MiB"
                )

        # Scope last: when a rule is both unscoped and broken, the broken reference is
        # the more useful complaint.
        try:
            css_audit.check_selector_scope(text, theme_id)
        except css_audit.CssAuditError as error:
            raise ExternalThemeError(f"{filename}：{error}") from error
    return metadata


def validate_installed_theme(theme_id: str) -> str:
    """Re-validate an installed user theme and return its directory.

    Called before any read that can end up inside a generated document. It re-checks
    what an *installed* directory has to satisfy on its own -- directory name equals
    metadata id, plus everything ``validate_theme_directory`` checks -- so a theme that
    was copied in by hand or edited after installation passes the same gate as one that
    came through ``import_theme``.
    """
    name = str(theme_id)
    if viewer_assets.theme_source(name) != viewer_assets.SOURCE_EXTERNAL:
        raise ExternalThemeError(f"未安装的外置主题：{name}")
    directory = viewer_assets.theme_dir(name)
    if os.path.basename(os.path.abspath(directory)) != name:
        raise ExternalThemeError(
            "安装目录名必须等于主题 id："
            + os.path.basename(directory)
            + " != "
            + name
        )
    metadata = validate_theme_directory(directory)
    if str(metadata.get("id")) != name:
        raise ExternalThemeError(
            "metadata.id 与安装目录名不一致：" + str(metadata.get("id")) + " != " + name
        )
    return directory


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
    """Return a theme's CSS with its local assets embedded, after re-validating it.

    The re-validation is the point: this is the last gate before the CSS becomes part
    of a delivered document, and the installed directory may have changed since it was
    imported. Replacement is span based and driven by ``css_audit.scan_references``,
    so the inliner and the validator cannot disagree about where a reference starts.
    """
    root = validate_installed_theme(theme_id)
    parts: list[str] = []
    for filename in viewer_assets.theme_files(theme_id):
        path = os.path.join(root, filename)
        css = _read_text(path)
        pieces: list[str] = []
        cursor = 0
        for reference in css_audit.scan_references(css):
            if reference.kind != "url":
                continue
            target = reference.target.strip()
            kind = css_audit.reference_kind(target)
            if kind in ("fragment", "data"):
                continue
            if kind == "remote":
                # 前置校验已经拒过；这里再拦一次，避免将来有人单独调用本函数。
                raise ExternalThemeError(
                    f"{filename} 引用了远程资源（{target}）：外置主题必须离线自包含"
                )
            uri, _ = _asset_payload(os.path.dirname(path), root, target, filename)
            pieces.append(css[cursor : reference.start])
            pieces.append('url("' + uri + '")')
            cursor = reference.end
        pieces.append(css[cursor:])
        parts.append("".join(pieces))
    return "\n".join(parts)


# The three facts one configured user theme can be. Both aggregators below share this
# table and differ only in what they do with "invalid": a document must not embed a
# theme it cannot trust, while the reader's state has to keep answering questions about
# every other id.
_STATE_MISSING = "missing"
_STATE_INVALID = "invalid"
_STATE_VALID = "valid"


def _classify_configured_theme(
    theme_id: str, installed: set[str]
) -> tuple[str, ExternalThemeError | None]:
    """Return ``(state, error)`` for one configured user theme id.

    It answers one question about one id: not ordering, not a whole selection and not
    the document default. ``resolve_theme_selection()`` and ``theme_state()`` both use
    it, so a rule change lands in one place -- and the exception object travels
    unchanged, so the conversion path keeps raising exactly what Phase 7 locked in.
    """
    if theme_id not in installed:
        return _STATE_MISSING, None
    try:
        validate_installed_theme(theme_id)
    except ExternalThemeError as error:
        return _STATE_INVALID, error
    return _STATE_VALID, None


def _document_default_warning(default: str | None) -> str | None:
    """Return why a document default theme is unusable, or ``None``.

    The order copies the two assembly paths exactly: ``viewer_assets.validate_theme()``
    first (missing / hidden / not selectable / broken inheritance), then the external
    theme's use-time gate. A non-selectable id such as ``base`` is already refused by the
    first gate, so it never reaches the external check by accident.
    """
    default_id = str(default) if default else ""
    if not default_id:
        return None
    try:
        viewer_assets.validate_theme(default_id)
    except ValueError as error:
        return "文档默认主题当前不可用：" + default_id + "（" + str(error) + "）"
    if viewer_assets.theme_source(default_id) != viewer_assets.SOURCE_EXTERNAL:
        return None
    try:
        validate_installed_theme(default_id)
    except ExternalThemeError as error:
        return "文档默认主题当前不可用：" + default_id + "（" + str(error) + "）"
    return None


def theme_state(configured: list[str] | None = None, *, default: str | None = None) -> dict:
    """Return what the configured user themes are worth right now (Phase 8C).

    ``resolve_theme_selection()`` answers "what does this document carry" and fails on a
    theme that must not be embedded; a reader's state has to answer "what can be restored
    today" instead, so a broken theme becomes a warning and every other id is still
    classified -- one bad theme must neither hide the ones that are fine nor the ones
    that are simply missing.

    Returns ``{"installed", "selected", "missing", "invalid", "warnings"}``.
    ``selected`` is a subsequence of the configured list, so it keeps the user's own
    order; the bundle's ``external_ids`` keeps its own deterministic sort.
    """
    installed = set(viewer_assets.external_theme_ids())
    selected: list[str] = []
    missing: list[str] = []
    invalid: list[str] = []
    warnings: list[str] = []

    for item in configured or []:
        theme_id = str(item)
        if theme_id in selected or theme_id in missing or theme_id in invalid:
            continue
        state, error = _classify_configured_theme(theme_id, installed)
        if state == _STATE_VALID:
            selected.append(theme_id)
        elif state == _STATE_MISSING:
            missing.append(theme_id)
            warnings.append("外置主题当前未安装：" + theme_id)
        else:
            invalid.append(theme_id)
            warnings.append(str(error) if error else "外置主题当前不可用：" + theme_id)

    default_warning = _document_default_warning(default)
    if default_warning:
        warnings.append(default_warning)
    return {
        "installed": sorted(installed),
        "selected": selected,
        "missing": missing,
        "invalid": invalid,
        "warnings": warnings,
    }


def resolve_theme_selection(
    requested: list[str] | None = None, *, default: str | None = None
) -> dict:
    """Resolve which user themes one document carries, and say why.

    Returns ``{"external_ids": [...], "menu_ids": [...], "warnings": [...]}``. This is
    the single place that answers the question, so the bundle, the reader's menu and
    the conversion report cannot disagree -- they did once: a document whose default
    theme was a user theme carried it while its menu did not offer it, which made
    switching away a one-way trip.

    Three outcomes, deliberately different:

    * a requested id that is not installed is ignored with a warning: a config that
      outlived a theme must not stop a conversion (AGENTS section 17);
    * a requested id that is installed but no longer valid fails here -- it would
      otherwise be embedded into the document as it is;
    * a document default that is an installed user theme is added even when the
      selection forgot it, with a warning.

    The classification comes from ``_classify_configured_theme()``, which ``theme_state()``
    uses for the reader's UI: the same facts, a different verdict for "installed but
    unusable" -- this function refuses to embed it, that one warns.
    """
    installed = set(viewer_assets.external_theme_ids())
    chosen: list[str] = []
    warnings: list[str] = []

    for item in requested or []:
        theme_id = str(item)
        if theme_id in chosen:
            continue
        state, error = _classify_configured_theme(theme_id, installed)
        if state == _STATE_MISSING:
            warnings.append("已忽略未安装的外置主题：" + theme_id)
            continue
        if error is not None:
            raise error
        chosen.append(theme_id)

    default_id = str(default) if default else ""
    if default_id and viewer_assets.theme_source(default_id) == viewer_assets.SOURCE_EXTERNAL:
        if default_id not in chosen:
            validate_installed_theme(default_id)
            warnings.append(
                "文档默认主题 " + default_id + " 未在选中列表里，已自动补入本文档。"
            )
            chosen.append(default_id)

    external_ids = sorted(chosen)
    return {
        "external_ids": external_ids,
        "menu_ids": sorted(set(viewer_assets.builtin_theme_ids()) | set(external_ids)),
        "warnings": warnings,
    }


def theme_bundle(selection: dict | None = None) -> list[dict]:
    """Return every theme a document carries: id, source and inline-ready CSS.

    Order is base, then the builtin themes, then the selected user themes. base holds
    the tokens; each selectable theme scopes its rules to its own id, so a later theme
    only wins for what it actually sets.

    A document whose default theme is an installed user theme carries it even when the
    selection forgot to mention it: the alternative is a document that opens in a theme
    it does not contain. Selecting a user theme also validates it, because the installed
    directory is a user asset and the CSS has to be safe *now*, not only when it was
    installed.
    """
    resolved = selection or {}
    order = [viewer_assets.BASE_THEME_ID, *viewer_assets.builtin_theme_ids()]
    order.extend(str(item) for item in (resolved.get("external_ids") or []))

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
