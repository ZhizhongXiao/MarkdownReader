"""Standalone closure checker for the Phase 5D gate.

Answers one question about a produced HTML document: **are its subresources
closed?**

    standalone          no external subresource at all
    degraded            a resource the resource layer owns could not be inlined and
                        the author reference was kept, with fallback evidence
                        (manifest status + readable warning)
    author_references   the external reference comes from the author's own raw HTML
                        (declared and corroborated) - neither a fallback nor a failure
    failure             an external subresource should have been closed and has
                        neither fallback evidence nor an author declaration

Severity is ordered `failure > degraded > author_references > standalone`, and the
report always keeps every bucket, so an author-owned reference can never hide a real
degradation or failure.

Evidence is consumed **per occurrence**, never per URL string. The manifest carries one
item per Markdown occurrence (three Markdown images of one URL are three items), and an
author declaration states how many occurrences it covers. For every reference:

    final external occurrences
        = degraded (kept, or failed with a warning that mentions the reference)
        + author (declared *and* corroborated by the renderer fragment)
        + unexplained

Degraded evidence claims occurrences first, so an author declaration can never turn a
real degradation into an author reference; a declaration that does not cover every
external occurrence leaves the rest unexplained and fails the gate. Evidence is
positive only: a reference counts as author-owned when the caller declares it
(`author_owned_refs`, a plain list and/or `{"ref": ..., "count": n}` entries) and the
renderer's own fragment (`envelope["html"]`) really contains that many occurrences.

`<a href>` is navigation, not a subresource, and the checker never looks at the literal
string "http" - the committed demo page contains three navigation links and is still
standalone. CSS is scanned both in `<style>` elements and in `style="..."` attributes:
K13 says the resource collector must not touch raw HTML, it does not say a browser will
not load what the author wrote there. A `<link>` counts only for `rel` values a browser
actually fetches; unknown or missing `rel` counts too, because a closure gate should be
noisy rather than quietly ignore a real subresource.
"""

import argparse
import json
import re
import sys
from collections.abc import Sequence
from html.parser import HTMLParser

# A value here must be closed (inlined) for the document to be standalone.
# `<a href>` and plain text are not listed.
SUB_RESOURCE_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "img": ("src",),
    "script": ("src",),
    "link": ("href",),
    "source": ("src",),
    "iframe": ("src",),
    "embed": ("src",),
    "object": ("data",),
    "video": ("poster",),
}
SRCSET_ATTRIBUTES: dict[str, tuple[str, ...]] = {"img": ("srcset",), "source": ("srcset",)}

# `<link>` rel values that do not make a browser load the target. Every other value
# (including an unknown or missing one) counts as a subresource on purpose.
NON_FETCHING_LINK_RELS = frozenset(
    {
        "alternate",
        "author",
        "bookmark",
        "canonical",
        "dns-prefetch",
        "help",
        "license",
        "me",
        "next",
        "pingback",
        "preconnect",
        "prev",
        "search",
        "tag",
        "webmention",
    }
)

# Controlled CSS: `url(...)` and string-form `@import` inside `<style>` elements, plus
# `url(...)` inside `style="..."` attributes (a browser loads those too).
CSS_URL_PATTERN = re.compile(r"""url\(\s*(?P<quote>["']?)(?P<ref>[^"'()]+)(?P=quote)\s*\)""")
CSS_IMPORT_PATTERN = re.compile(r"""@import\s+(?P<quote>["'])(?P<ref>[^"']+)(?P=quote)""")
SRCSET_TOKEN_PATTERN = re.compile(r"\S+")

# Anything else (http/https/file/relative/absolute paths) is an external subresource.
INLINE_PREFIXES = ("data:", "about:", "#")

def _link_reference_is_fetched(rel: str | None) -> bool:
    """Return True when a `<link>` rel value makes a browser load the target."""
    tokens = {token.strip().lower() for token in str(rel or "").split()}
    return not (tokens & NON_FETCHING_LINK_RELS)


def srcset_references(value: str) -> list[str]:
    """Return the URLs of a `srcset` attribute, following the HTML parser algorithm.

    Splitting on commas is wrong: a data URI contains one (`data:image/png;base64,AAAA
    1x` would yield the pseudo reference `AAAA`). A URL is a maximal non-whitespace run,
    and a candidate ends at the descriptor carrying the separating comma or at the end
    of the value, so commas inside a URL survive.
    """
    references: list[str] = []
    position = 0
    length = len(value)
    while position < length:
        while position < length and (value[position].isspace() or value[position] == ","):
            position += 1
        url_match = SRCSET_TOKEN_PATTERN.match(value, position)
        if url_match is None:
            break
        url = url_match.group(0)
        position = url_match.end()
        if url.endswith(","):
            # URL-only candidate: the trailing comma is the separator, not the URL.
            candidate = url.rstrip(",")
            if candidate:
                references.append(candidate)
            continue
        while True:
            while position < length and value[position].isspace():
                position += 1
            descriptor = SRCSET_TOKEN_PATTERN.match(value, position)
            if descriptor is None:
                break
            position = descriptor.end()
            if descriptor.group(0).endswith(","):
                break
        references.append(url)
    return references


def _css_references(css: str, *, string_imports: bool) -> list[tuple[str, str]]:
    """Return `(reference, form)` for every `url()` and string-form `@import`."""
    found = [(match.group("ref").strip(), "url()") for match in CSS_URL_PATTERN.finditer(css)]
    if string_imports:
        found.extend(
            (match.group("ref").strip(), "@import") for match in CSS_IMPORT_PATTERN.finditer(css)
        )
    return found


class _SubresourceCollector(HTMLParser):
    """Collect subresource references, `style` attributes and `<style>` text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, str, str]] = []
        self.style_attributes: list[tuple[str, str]] = []
        self._style_depth = 0
        self._style_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        values = {attribute.lower(): value for attribute, value in attrs if value is not None}
        for attribute in SUB_RESOURCE_ATTRIBUTES.get(name, ()):
            value = values.get(attribute)
            if not value:
                continue
            if name == "link" and not _link_reference_is_fetched(values.get("rel")):
                continue
            reference = value.strip()
            if reference:
                self.references.append((name, attribute, reference))
        for attribute in SRCSET_ATTRIBUTES.get(name, ()):
            value = values.get(attribute)
            if not value:
                continue
            for reference in srcset_references(value):
                self.references.append((name, attribute, reference))
        style_attribute = values.get("style")
        if style_attribute:
            self.style_attributes.append((name, style_attribute))
        if name == "style":
            self._style_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style" and self._style_depth:
            self._style_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._style_depth:
            self._style_chunks.append(data)

    def style_text(self) -> str:
        """Return the concatenated text of every `<style>` element."""
        return "".join(self._style_chunks)


def is_inline_reference(reference: str) -> bool:
    """Return True when a reference needs no closure (data URI, fragment, empty)."""
    value = str(reference).strip().lower()
    return not value or value.startswith(INLINE_PREFIXES)


def collect_subresources(html: str) -> list[dict]:
    """Return every subresource reference: attributes, `style` attributes, then CSS."""
    parser = _SubresourceCollector()
    parser.feed(html)
    parser.close()

    found = [
        {"ref": reference, "origin": "attr", "element": element, "attribute": attribute}
        for element, attribute, reference in parser.references
    ]
    for element, css in parser.style_attributes:
        for reference, _form in _css_references(css, string_imports=False):
            found.append(
                {
                    "ref": reference,
                    "origin": "style-attr",
                    "element": element,
                    "attribute": "style",
                }
            )
    style_css = parser.style_text()
    for reference, form in _css_references(style_css, string_imports=True):
        found.append({"ref": reference, "origin": "css", "element": "style", "attribute": form})
    return found


def _manifest_items(envelope: dict | None) -> dict[str, list[dict]]:
    """Index manifest items by reference; the manifest carries one item per occurrence."""
    items = ((envelope or {}).get("resources") or {}).get("items") or []
    index: dict[str, list[dict]] = {}
    for item in items:
        reference = str((item or {}).get("ref") or "")
        if reference:
            index.setdefault(reference, []).append(item)
    return index


def _author_counts(author_owned_refs) -> dict[str, int]:
    """Normalise author declarations to `{reference: occurrences}`.

    Accepts a plain list of references (one occurrence each), entries shaped like
    `{"ref": ..., "count": n}`, or both mixed; counts are additive.
    """
    counts: dict[str, int] = {}
    for entry in author_owned_refs or ():
        if isinstance(entry, dict):
            reference = str(entry.get("ref") or "")
            raw_count = entry.get("count", 1)
        else:
            reference = str(entry)
            raw_count = 1
        if not reference:
            continue
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            count = 1
        if count > 0:
            counts[reference] = counts.get(reference, 0) + count
    return counts


def _occurrences(references: list[str]) -> dict[str, int]:
    """Count occurrences per reference, preserving first-seen (document) order."""
    counts: dict[str, int] = {}
    for reference in references:
        counts[reference] = counts.get(reference, 0) + 1
    return counts


def _warning_for(reference: str, warnings: list) -> str | None:
    """Return the first readable warning that mentions this reference."""
    for warning in warnings or ():
        text = str(warning)
        if reference and reference in text:
            return text
    return None

def payload_report(html: str, injections: list | None) -> dict:
    """Return the size report derived from the assembler's injection ledger."""
    parts: list[dict] = []
    for item in injections or ():
        entry = item or {}
        parts.append(
            {
                "position": str(entry.get("position") or ""),
                "label": str(entry.get("label") or ""),
                "id": entry.get("id"),
                "bytes": int(entry.get("bytes") or 0),
            }
        )
    injected = sum(part["bytes"] for part in parts)
    total = len(html.encode("utf-8"))
    return {
        "total_bytes": total,
        "injected_bytes": injected,
        "document_bytes": total - injected,
        "resource_payload_bytes": sum(
            part["bytes"]
            for part in parts
            if part["label"].startswith(("style:", "script:", "boot:"))
        ),
        "parts": parts,
    }


def scan(
    html: str,
    *,
    envelope: dict | None = None,
    injections: list | None = None,
    author_owned_refs=(),
) -> dict:
    """Classify every subresource in `html` and return the closure verdict."""
    manifest = _manifest_items(envelope)
    warnings = list((envelope or {}).get("warnings") or [])
    fragment = str((envelope or {}).get("html") or "")
    declared = _author_counts(author_owned_refs)

    subresources = collect_subresources(html)
    occurrences = _occurrences(
        [entry["ref"] for entry in subresources if not is_inline_reference(entry["ref"])]
    )

    degraded: list[dict] = []
    author: list[dict] = []
    unexplained: list[dict] = []
    problems: list[str] = []
    ledger: list[dict] = []
    assignment: dict[str, list[str]] = {}

    for reference, final_count in occurrences.items():
        items = manifest.get(reference, [])
        statuses = [str((item or {}).get("status") or "") for item in items]
        inlined_count = statuses.count("inlined")
        failed_count = statuses.count("failed")
        kept_count = statuses.count("kept")
        warning = _warning_for(reference, warnings)
        declared_count = declared.get(reference, 0)
        corroborated = min(declared_count, fragment.count(reference))

        # 5C emits one warning per failing URL, so it covers every failed occurrence.
        # Degraded evidence claims occurrences first: a declaration can never turn a
        # real degradation into an author reference.
        degradable = kept_count + (failed_count if warning is not None else 0)
        consumed_degraded = min(final_count, degradable)
        consumed_author = min(final_count - consumed_degraded, corroborated)
        leftover = final_count - consumed_degraded - consumed_author

        if consumed_degraded:
            degraded.append(
                {
                    "ref": reference,
                    "occurrences": consumed_degraded,
                    "evidence": {
                        "kind": "manifest",
                        "kept": kept_count,
                        "failed": failed_count,
                        "warning": warning,
                    },
                }
            )
        if consumed_author:
            author.append(
                {
                    "ref": reference,
                    "occurrences": consumed_author,
                    "evidence": {
                        "kind": "declared",
                        "declared": declared_count,
                        "corroborated_by": "envelope.html",
                    },
                }
            )
        if leftover:
            hints: list[str] = []
            if inlined_count:
                hints.append("manifest 记为 inlined")
            if failed_count and warning is None:
                hints.append("failed 项缺少 warning 证据")
            if declared_count and corroborated < final_count:
                hints.append(f"作者声明只覆盖 {corroborated} 处")
            if not items and not declared_count:
                hints.append("既不在资源 manifest，也未被声明为作者 raw HTML")
            detail = "；".join(hints) if hints else "缺少可消费的证据"
            problems.append(
                f"{reference}：最终有 {final_count} 处外部引用，"
                f"{leftover} 处无法解释（{detail}）。"
            )
            unexplained.append(
                {"ref": reference, "occurrences": leftover, "evidence": {"kind": "none"}}
            )
        if failed_count and warning is None:
            problems.append(f"{reference}：manifest 记为 failed，但没有提及该引用的 warning。")

        assignment[reference] = (
            ["degraded"] * consumed_degraded
            + ["author"] * consumed_author
            + ["unexplained"] * leftover
        )
        ledger.append(
            {
                "ref": reference,
                "final": final_count,
                "degraded": consumed_degraded,
                "author": consumed_author,
                "unexplained": leftover,
                "manifest": {
                    "inlined": inlined_count,
                    "failed": failed_count,
                    "kept": kept_count,
                },
                "declared_author": declared_count,
                "warning": warning,
            }
        )

    # Give every occurrence in document order the status its reference was assigned.
    entries: list[dict] = []
    consumed: dict[str, int] = {}
    for subresource in subresources:
        reference = subresource["ref"]
        if is_inline_reference(reference):
            entries.append({**subresource, "status": "inline"})
            continue
        index = consumed.get(reference, 0)
        consumed[reference] = index + 1
        statuses_for_reference = assignment.get(reference, [])
        if index >= len(statuses_for_reference):
            status = "unexplained"
        else:
            status = statuses_for_reference[index]
        entries.append({**subresource, "status": status})

    # Declaration audit: a declaration must be corroborated by the renderer fragment and
    # must actually describe the produced document.
    for reference in sorted(declared):
        declared_count = declared[reference]
        corroborated = min(declared_count, fragment.count(reference))
        if declared_count > corroborated:
            problems.append(
                f"{reference}：声明了 {declared_count} 处作者 raw HTML，"
                f"但 renderer fragment 里只有 {corroborated} 处。"
            )
        if reference not in html:
            problems.append(f"{reference}：声明为作者 raw HTML，但最终文档里没有该引用。")

    if problems:
        verdict = "failure"
    elif degraded:
        verdict = "degraded"
    elif author:
        verdict = "author_references"
    else:
        verdict = "standalone"

    return {
        "verdict": verdict,
        "severity_order": ["failure", "degraded", "author_references", "standalone"],
        "standalone": verdict == "standalone",
        "degraded_resources": degraded,
        "author_references": author,
        "unexplained_external_resources": unexplained,
        "occurrences": ledger,
        "subresources": entries,
        "problems": problems,
        "payload": payload_report(html, injections),
    }

def _load_json(path: str | None):
    """Load a JSON document, or return None when no path was given."""
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "检查一份 HTML 的 standalone closure（Phase 5D）。"
            "不提供 --envelope 时走 strict 模式：任何外部 subresource 都判 failure。"
        ),
    )
    parser.add_argument("html", help="要检查的 HTML 文件路径")
    parser.add_argument(
        "--envelope",
        help="renderer v2 envelope JSON；提供后才有 manifest / warning 证据",
    )
    parser.add_argument(
        "--author-refs",
        help='JSON 数组：声明为作者 raw HTML 的外部引用，例如 ["https://x/a.png"] '
        '或 [{"ref": "https://x/a.png", "count": 2}]',
    )
    parser.add_argument("--injections", help="JSON 数组：assembler 注入账本（体积报告用）")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the checker as a CLI; exit code 1 when the verdict is `failure`."""
    args = _build_parser().parse_args(argv)
    with open(args.html, "r", encoding="utf-8") as handle:
        html = handle.read()

    report = scan(
        html,
        envelope=_load_json(args.envelope),
        injections=_load_json(args.injections),
        author_owned_refs=_load_json(args.author_refs) or (),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["verdict"] == "failure" else 0


if __name__ == "__main__":
    sys.exit(main())
