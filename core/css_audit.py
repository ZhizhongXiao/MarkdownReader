"""CSS analysis for the two places that must not be fooled by CSS syntax.

Two consumers, one scanner:

* an external theme is audited before its CSS can reach a generated document -- at
  import time **and again at every read**, because an installed theme is a persistent
  user asset that may be edited afterwards; and
* the standalone closure checker scans whatever CSS a document carries.

A regular expression cannot do this job. `url("…/a(b).png")` is legal CSS that the
previous pattern could not see at all, and any regex that must also feed a
replacement turns into a second, subtly different parser. This module is instead a
small scanner over a documented subset, and it returns spans so the inliner replaces
exactly what was scanned.

Fail-closed: whatever the scanner cannot prove it understands is refused --
unterminated comments or strings, unbalanced parentheses, a CSS escape inside a
`url()` target (so `url("https\\3a //example.invalid/x")` cannot hide a scheme), NUL and
control characters, a bare `url()` argument containing parentheses, and the resource
functions this subset does not audit (`image-set()` takes a plain string as an image
URL, `src()` is the other spelling of <url>, and `image()`/`cross-fade()`/`element()`
are unproven here). A gradient needs no refusal: it cannot name a file or a host.
"""

import re
from dataclasses import dataclass


class CssAuditError(ValueError):
    """Raised when CSS cannot be analysed with confidence, or breaks a theme rule."""


@dataclass(frozen=True)
class CssReference:
    """One `url()` or `@import` occurrence: what it points at and where it sits."""

    kind: str
    target: str
    start: int
    end: int
    raw: str


# Resource functions this subset does not audit. `image-set()` accepts a bare
# <string> as an image URL and `src()` is the other spelling of <url> (CSS Values 4),
# so a legal stylesheet could name a remote image without ever writing `url(`.
# Refusing them keeps the "zero network" promise provable, and a gradient stays legal:
# it cannot name a file or a host.
UNAUDITED_RESOURCE_FUNCTIONS = (
    "-webkit-image-set(",
    "image-set(",
    "cross-fade(",
    "element(",
    "image(",
    "src(",
)

_URL_FUNCTION = "url("
_IMPORT_RULE = "@import"
_WHITESPACE = " \t\r\n\f"
_QUOTES = "\"'"


def _is_control(char: str) -> bool:
    """Return True for C0/C1 controls and NUL, which have no place in a theme."""
    code = ord(char)
    return code == 0 or (code < 0x20 and char not in "\t\n\r\f") or 0x7F <= code < 0xA0


def _skip_comment(css: str, index: int) -> int:
    """Return the index after the `/* ... */` starting at ``index``."""
    end = css.find("*/", index + 2)
    if end == -1:
        raise CssAuditError("CSS 注释未闭合")
    return end + 2


def _skip_string(css: str, index: int) -> int:
    """Return the index after the string starting at ``index`` (a quote).

    CSS escapes inside a string are skipped as pairs: their meaning does not matter
    here, only that the string ends where it claims to.
    """
    quote = css[index]
    cursor = index + 1
    length = len(css)
    while cursor < length:
        char = css[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == quote:
            return cursor + 1
        cursor += 1
    raise CssAuditError("CSS 字符串未闭合")


def _skip_whitespace(css: str, index: int) -> int:
    while index < len(css) and css[index] in _WHITESPACE:
        index += 1
    return index


def _target_from_reference(raw: str) -> str:
    """Return a quoted url()/@import target, refusing CSS escapes (fail closed).

    Refusing instead of decoding is the point: ``url("https\\3a //example.invalid/x")``
    is a valid CSS spelling of a remote URL, and a decoder that gets one case wrong is
    worse than a rule that says themes may not escape URLs at all.
    """
    if "\\" in raw:
        raise CssAuditError("url() / @import 的目标不得使用 CSS 转义")
    for char in raw:
        if _is_control(char):
            raise CssAuditError("url() / @import 的目标不得包含控制字符")
    return raw.strip()


def _read_url_reference(css: str, index: int) -> CssReference:
    """Read the ``url(...)`` starting at ``index``, quoted or bare argument."""
    cursor = _skip_whitespace(css, index + len(_URL_FUNCTION))
    if cursor >= len(css):
        raise CssAuditError("url() 缺少参数")
    if css[cursor] in _QUOTES:
        end = _skip_string(css, cursor)
        target = _target_from_reference(css[cursor + 1 : end - 1])
        cursor = end
    else:
        start = cursor
        while cursor < len(css) and css[cursor] != ")":
            char = css[cursor]
            if char == "(":
                raise CssAuditError("url() 的裸参数不得包含括号")
            if char == "\\":
                raise CssAuditError("url() 参数不得使用 CSS 转义")
            if _is_control(char):
                raise CssAuditError("url() 参数不得包含控制字符")
            cursor += 1
        if cursor >= len(css):
            raise CssAuditError("url() 缺少右括号")
        target = css[start:cursor].strip()
    cursor = _skip_whitespace(css, cursor)
    if cursor >= len(css) or css[cursor] != ")":
        raise CssAuditError("url() 缺少右括号")
    end = cursor + 1
    return CssReference("url", target, index, end, css[index:end])


def _read_import_reference(css: str, index: int) -> CssReference:
    """Read the ``@import`` starting at ``index`` (string or url() form)."""
    cursor = _skip_whitespace(css, index + len(_IMPORT_RULE))
    if css[cursor : cursor + len(_URL_FUNCTION)].lower() == _URL_FUNCTION:
        inner = _read_url_reference(css, cursor)
        return CssReference("import", inner.target, index, inner.end, css[index : inner.end])
    if cursor < len(css) and css[cursor] in _QUOTES:
        end = _skip_string(css, cursor)
        target = _target_from_reference(css[cursor + 1 : end - 1])
        return CssReference("import", target, index, end, css[index:end])
    raise CssAuditError("@import 形式无法识别（只支持字符串或 url()）")


def scan_references(css: str) -> list[CssReference]:
    """Return every ``url()`` and ``@import`` in ``css``, refusing anything unclear.

    This is the one scanner behind the theme validator, the asset inliner and the
    standalone checker. It never looks inside strings or comments, so
    ``content: "url(http://x)"`` is content, and it refuses rather than guesses.
    """
    references: list[CssReference] = []
    cursor = 0
    length = len(css)
    while cursor < length:
        char = css[cursor]
        if char == "/" and css.startswith("/*", cursor):
            cursor = _skip_comment(css, cursor)
            continue
        if char in _QUOTES:
            cursor = _skip_string(css, cursor)
            continue
        unaudited = next(
            (
                name
                for name in UNAUDITED_RESOURCE_FUNCTIONS
                if css[cursor : cursor + len(name)].lower() == name
            ),
            None,
        )
        if unaudited:
            raise CssAuditError("未审计的 CSS 资源函数（本阶段直接拒绝）：" + unaudited)
        if css[cursor : cursor + len(_URL_FUNCTION)].lower() == _URL_FUNCTION:
            reference = _read_url_reference(css, cursor)
            references.append(reference)
            cursor = reference.end
            continue
        if css[cursor : cursor + len(_IMPORT_RULE)].lower() == _IMPORT_RULE:
            reference = _read_import_reference(css, cursor)
            references.append(reference)
            cursor = reference.end
            continue
        if char == "\\":
            raise CssAuditError("CSS 出现孤立的反斜杠转义")
        if _is_control(char):
            raise CssAuditError("CSS 出现控制字符")
        cursor += 1
    return references

# ---------------------------------------------------------------------------
# External theme policy
# ---------------------------------------------------------------------------

# Markup or script that would escape the <style> element the theme is embedded in, or
# that can run code from CSS. Checked on the lowercased text: refusing a token that
# only appears inside a comment or a string is acceptable, silently allowing it is not.
FORBIDDEN_TOKENS = (
    ("@import", "@import"),
    ("</style", "</style"),
    ("<script", "<script"),
    ("javascript:", "javascript"),
    ("expression(", "expression"),
    ("behavior:", "behavior"),
    ("-moz-binding", "-moz-binding"),
)

# A data URI is inline by definition, but not automatically safe: `data:text/html` or
# an SVG can carry markup. Phase 7 allows the media types a reading theme actually
# needs and refuses the rest, SVG included (it would need its own content audit).
ALLOWED_DATA_MIME = (
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "font/woff",
    "font/woff2",
    "font/ttf",
    "font/otf",
)

SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")
SCOPED_AT_RULES = ("@media", "@supports")


def reference_kind(target: str) -> str:
    """Classify a reference target: ``fragment``, ``data``, ``remote`` or ``local``."""
    lowered = target.lower()
    if target.startswith("#"):
        return "fragment"
    if lowered.startswith("data:"):
        return "data"
    if lowered.startswith("//") or SCHEME_PATTERN.match(target):
        return "remote"
    return "local"


def data_uri_mime(target: str) -> str:
    """Return the media type of a ``data:`` URI, lowercased and without parameters."""
    header = target.split(",", 1)[0]
    mime = header.split(";", 1)[0]
    return mime[len("data:") :].strip().lower()


def _strip_comments(text: str) -> str:
    """Return ``text`` without comments, for places that only look at the text."""
    pieces: list[str] = []
    cursor = 0
    while True:
        start = text.find("/*", cursor)
        if start == -1:
            pieces.append(text[cursor:])
            break
        pieces.append(text[cursor:start])
        end = text.find("*/", start + 2)
        if end == -1:
            raise CssAuditError("CSS 注释未闭合")
        cursor = end + 2
    return "".join(pieces)


def _split_selectors(prelude: str) -> list[str]:
    """Split a selector list on top-level commas only."""
    items: list[str] = []
    depth = 0
    current = ""
    cursor = 0
    while cursor < len(prelude):
        char = prelude[cursor]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            items.append(current)
            current = ""
        else:
            current += char
        cursor += 1
    items.append(current)
    return items


def check_selector_scope(css: str, theme_id: str) -> None:
    """Refuse any rule that is not scoped to this theme id.

    Every style rule must start with ``html[data-theme-id="<id>"]`` -- the canonical
    spelling, not an equivalent selector built with ``:is()`` or escapes. A theme is a
    visual layer for one id; a global rule would outlive a theme switch and keep
    polluting the reader (Phase 6 gave each theme its own scope for that reason).

    ``@media`` and ``@supports`` are recursed into. Every other at-rule is refused:
    ``@keyframes`` and ``@font-face`` own global names, ``@page`` cannot be scoped,
    and ``@charset``/``@layer``/``@namespace`` have no meaning for a file that Python
    reads as UTF-8 and concatenates with other files.
    """
    prefix = 'html[data-theme-id="' + theme_id + '"]'
    modes: list[str] = []
    prelude_start = 0
    cursor = 0
    length = len(css)
    while cursor < length:
        char = css[cursor]
        if char == "/" and css.startswith("/*", cursor):
            cursor = _skip_comment(css, cursor)
            continue
        if char in _QUOTES:
            cursor = _skip_string(css, cursor)
            continue
        if char == "{":
            prelude = _strip_comments(css[prelude_start:cursor]).strip()
            if prelude.startswith("@"):
                name = prelude.split(None, 1)[0].lower()
                if name not in SCOPED_AT_RULES:
                    raise CssAuditError(f"不允许的 at-rule：{name}")
                modes.append("at")
            else:
                if not prelude:
                    raise CssAuditError("出现空选择器")
                for item in _split_selectors(prelude):
                    if not item.strip().startswith(prefix):
                        raise CssAuditError(
                            "主题规则必须 scoped 到 " + prefix + "：" + item.strip()[:60]
                        )
                modes.append("rule")
            prelude_start = cursor + 1
        elif char == "}":
            if not modes:
                raise CssAuditError("多余的 }")
            modes.pop()
            prelude_start = cursor + 1
        elif char == ";" and (not modes or modes[-1] == "at"):
            segment = _strip_comments(css[prelude_start:cursor]).strip()
            if segment:
                raise CssAuditError("不允许的 at-rule 或顶层文本：" + segment[:40])
            prelude_start = cursor + 1
        cursor += 1
    if modes:
        raise CssAuditError("大括号不闭合")


def check_theme_references(css: str, theme_id: str) -> list[CssReference]:
    """Check the references of one theme stylesheet and return them.

    This is the half that is about leaving the document (forbidden tokens, remote or
    non-allow-listed data URIs); ``check_selector_scope`` is the half about leaking
    into other themes. They are separate so a caller can look at the referenced assets
    before reporting a scope problem.
    """
    lowered = css.lower()
    for needle, reason in FORBIDDEN_TOKENS:
        if needle in lowered:
            raise CssAuditError(f"含有被禁止的内容：{reason}")

    references = scan_references(css)
    for reference in references:
        if reference.kind == "import":
            raise CssAuditError(
                "不得使用 @import（" + reference.target + "）：外置主题必须离线自包含"
            )
        kind = reference_kind(reference.target)
        if kind == "remote":
            raise CssAuditError(
                "引用了远程资源（" + reference.target + "）：外置主题必须离线自包含"
            )
        if kind == "data":
            mime = data_uri_mime(reference.target)
            if mime not in ALLOWED_DATA_MIME:
                raise CssAuditError(
                    "data URI 的媒体类型不被允许：" + (mime or "(空)")
                )

    return references


def audit_external_theme_css(css: str, theme_id: str) -> list[CssReference]:
    """Run the whole external theme policy over one stylesheet.

    Called at import time and again whenever the theme is read for a document: a theme
    that was valid when it was installed may have been edited since, and the installed
    directory is a persistent user asset.
    """
    references = check_theme_references(css, theme_id)
    check_selector_scope(css, theme_id)
    return references
