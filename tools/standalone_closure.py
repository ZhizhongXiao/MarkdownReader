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

Evidence is **positive only**: a reference counts as author-owned when the caller
declares it (`author_owned_refs`) *and* the renderer's own fragment
(`envelope["html"]`) really contains it. Everything else is `failure`, so a
collector regression (a Markdown image the resource layer failed to claim) can never
be re-labelled as an author reference.

`<a href>` is navigation, not a subresource, and the checker never looks at the
literal string "http" - the committed demo page contains three navigation links and
is still standalone.
"""

import argparse
import json
import re
import sys
from collections.abc import Sequence
from html.parser import HTMLParser

# A value here must be closed (inlined) for the document to be standalone.
# `<a href>`, `<link rel="canonical">`-style metadata and plain text are not listed.
SUB_RESOURCE_ATTRIBUTES = frozenset(
    {
        ("img", "src"),
        ("script", "src"),
        ("link", "href"),
        ("source", "src"),
        ("iframe", "src"),
        ("embed", "src"),
        ("object", "data"),
        ("video", "poster"),
    }
)
SRCSET_ATTRIBUTES = frozenset({("img", "srcset"), ("source", "srcset")})

# Controlled CSS: `url(...)` inside `<style>` elements (our injected stylesheets and
# any author-written `<style>` block). Inline `style="..."` attributes are author
# markup and deliberately out of scope (K13).
CSS_URL_PATTERN = re.compile(r"""url\(\s*(?P<quote>["']?)(?P<ref>[^"'()]+)(?P=quote)\s*\)""")

# Anything else (http/https/file/relative/absolute paths) is an external subresource.
INLINE_PREFIXES = ("data:", "about:", "#")

class _SubresourceCollector(HTMLParser):
    """Collect subresource references and `<style>` text (stdlib only, no DOM)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, str, str]] = []
        self._style_depth = 0
        self._style_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        for attribute, value in attrs:
            if value is None:
                continue
            key = (name, attribute.lower())
            if key in SUB_RESOURCE_ATTRIBUTES:
                reference = value.strip()
                if reference:
                    self.references.append((name, attribute.lower(), reference))
            elif key in SRCSET_ATTRIBUTES:
                for candidate in value.split(","):
                    reference = candidate.strip().split()[0] if candidate.strip() else ""
                    if reference:
                        self.references.append((name, attribute.lower(), reference))
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
    """Return every subresource reference, attributes first then CSS `url()`."""
    parser = _SubresourceCollector()
    parser.feed(html)
    parser.close()

    found = [
        {"ref": reference, "origin": "attr", "element": element, "attribute": attribute}
        for element, attribute, reference in parser.references
    ]
    for match in CSS_URL_PATTERN.finditer(parser.style_text()):
        found.append(
            {
                "ref": match.group("ref").strip(),
                "origin": "css",
                "element": "style",
                "attribute": "url()",
            }
        )
    return found


def _manifest_index(envelope: dict | None) -> dict[str, dict]:
    """Index manifest items by their author reference."""
    items = ((envelope or {}).get("resources") or {}).get("items") or []
    index: dict[str, dict] = {}
    for item in items:
        reference = str((item or {}).get("ref") or "")
        if reference:
            index.setdefault(reference, item)
    return index


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
    manifest = _manifest_index(envelope)
    warnings = list((envelope or {}).get("warnings") or [])
    fragment = str((envelope or {}).get("html") or "")
    declared = {str(reference) for reference in author_owned_refs or ()}

    degraded: list[dict] = []
    author: list[dict] = []
    unexplained: list[dict] = []
    entries: list[dict] = []
    problems: list[str] = []

    for subresource in collect_subresources(html):
        reference = subresource["ref"]
        if is_inline_reference(reference):
            entries.append({**subresource, "status": "inline"})
            continue

        item = manifest.get(reference)
        if item is not None:
            status = "degraded"
            item_status = str(item.get("status") or "")
            warning = _warning_for(reference, warnings)
            if item_status == "inlined":
                problems.append(f"{reference}：manifest 记为 inlined，但最终文档仍是外部引用。")
                status = "unexplained"
            elif item_status == "failed" and warning is None:
                problems.append(f"{reference}：manifest 记为 failed，但没有提及该引用的 warning。")
                status = "unexplained"
            if status == "degraded":
                evidence = {
                    "kind": "manifest",
                    "status": item_status,
                    "source": item.get("source"),
                    "warning": warning,
                }
                if reference in declared:
                    evidence["also_declared_as_author"] = True
                degraded.append({"ref": reference, "evidence": evidence})
            else:
                evidence = {"kind": "manifest", "status": item_status}
                unexplained.append({"ref": reference, "evidence": evidence})
        elif reference in declared:
            if reference in fragment:
                author.append(
                    {
                        "ref": reference,
                        "evidence": {
                            "kind": "declared",
                            "source": "raw HTML",
                            "corroborated_by": "envelope.html",
                        },
                    }
                )
                status = "author"
            else:
                problems.append(f"{reference}：声明为作者 raw HTML，但 fragment 里没有它。")
                unexplained.append(
                    {"ref": reference, "evidence": {"kind": "uncorroborated_declaration"}}
                )
                status = "unexplained"
        else:
            problems.append(
                f"{reference}：既不在资源 manifest，也未被声明为作者 raw HTML"
                "（可能是漏收集的 Markdown 资源）。"
            )
            unexplained.append({"ref": reference, "evidence": {"kind": "none"}})
            status = "unexplained"

        entries.append({**subresource, "status": status})

    for reference in sorted(declared):
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
    parser.add_argument("--author-refs", help="JSON 数组：声明为作者 raw HTML 的外部引用")
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
