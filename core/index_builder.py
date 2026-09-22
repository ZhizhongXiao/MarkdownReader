"""Build the standalone document index used by batch conversion."""

import logging
import os
from collections import defaultdict
from html import escape
from pathlib import PurePosixPath
from urllib.parse import quote

from core.config import BUNDLE_ROOT

_logger = logging.getLogger(__name__)

DEFAULT_INDEX_FILENAME = "index.html"

_INDEX_TEMPLATE_DIR = os.path.join(BUNDLE_ROOT, "templates", "index")
_INDEX_HTML = os.path.join(_INDEX_TEMPLATE_DIR, "index.html")
_INDEX_CSS = os.path.join(_INDEX_TEMPLATE_DIR, "theme.css")
_INDEX_JS = os.path.join(_INDEX_TEMPLATE_DIR, "index.js")


def make_index_filename(source_name: str = "") -> str:
    """Return the batch index filename for a selected source directory."""
    name = str(source_name or "").strip()
    return f"索引-{name}.html" if name else DEFAULT_INDEX_FILENAME


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as stream:
        return stream.read()


def _load_index_assets() -> tuple[str, str, str]:
    """Load index page shell assets from templates/index."""
    missing = [
        path
        for path in (_INDEX_HTML, _INDEX_CSS, _INDEX_JS)
        if not os.path.isfile(path)
    ]
    if missing:
        raise RuntimeError("索引模板资源缺失：%s" % ", ".join(missing))
    return _read_text(_INDEX_HTML), _read_text(_INDEX_CSS), _read_text(_INDEX_JS)


def _normalized_relative_path(filename: object) -> str:
    return str(filename or "").replace("\\", "/").strip("/")


def _render_document(doc: dict, folder: str = "") -> str:
    filename = _normalized_relative_path(doc.get("filename", ""))
    fallback_title = PurePosixPath(filename).stem if filename else "未命名文档"
    title = str(doc.get("title") or fallback_title)
    href = escape(quote(filename, safe="/"), quote=True)
    safe_title = escape(title)
    search_text = escape(f"{title} {folder}".lower(), quote=True)
    return (
        f'<div class="document-row" data-search="{search_text}">'
        f'<a class="document-title" href="{href}" target="_blank" '
        f'rel="noopener">{safe_title}</a>'
        f'<a class="document-open" href="{href}" target="_blank" '
        'rel="noopener" title="新标签页打开">↗</a>'
        "</div>"
    )


def _split_documents(documents: list[dict]) -> tuple[list[dict], dict[str, list[dict]]]:
    root_documents: list[dict] = []
    groups: dict[str, list[dict]] = defaultdict(list)

    for doc in documents:
        filename = _normalized_relative_path(doc.get("filename", ""))
        parent = PurePosixPath(filename).parent.as_posix() if filename else "."
        if parent == ".":
            root_documents.append(doc)
        else:
            groups[parent].append(doc)

    return root_documents, dict(groups)


def _render_items(documents: list[dict]) -> str:
    if not documents:
        return '<p class="empty">暂无文档</p>'

    root_documents, groups = _split_documents(documents)
    sections: list[str] = []

    if root_documents:
        rows = "".join(_render_document(doc) for doc in root_documents)
        sections.append(f'<div class="root-list">{rows}</div>')

    for folder in sorted(groups, key=str.casefold):
        docs = groups[folder]
        rows = "".join(_render_document(doc, folder) for doc in docs)
        safe_folder = escape(folder, quote=True)
        display_name = escape(folder.replace("/", " / "))
        sections.append(
            '<section class="folder-group" '
            f'data-folder="{safe_folder}">'
            '<div class="folder-header">'
            '<button class="toggle-btn" type="button" aria-expanded="true" '
            'title="折叠文件夹">▼</button>'
            '<span class="folder-mark" aria-hidden="true">▰</span>'
            f'<span class="folder-name">{display_name}</span>'
            '<span class="folder-actions">'
            f'<span class="folder-count">{len(docs)} 份</span>'
            '<button class="copy-btn" type="button" title="复制绝对路径">⧉</button>'
            "</span></div>"
            f'<div class="document-list">{rows}</div>'
            "</section>"
        )

    return "\n".join(sections)


def _build_html(page_title: str, heading: str, documents: list[dict]) -> str:
    html_template, css, js = _load_index_assets()
    replacements = {
        "{{PAGE_TITLE}}": escape(page_title),
        "{{HEADING}}": escape(heading),
        "{{COUNT}}": str(len(documents)),
        "{{ITEMS}}": _render_items(documents),
        "{{STYLE}}": css,
        "{{SCRIPT}}": js,
    }
    html = html_template
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)
    return html


def build_index(
    output_dir: str,
    documents: list[dict],
    filename: str = DEFAULT_INDEX_FILENAME,
    collection_name: str = "",
) -> str:
    """Generate a searchable standalone index in the output directory."""
    heading = str(collection_name or "文档索引")
    page_title = f"{heading} - 文档索引" if collection_name else heading
    html = _build_html(page_title, heading, documents)

    output_path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as stream:
        stream.write(html)

    _logger.info("索引页已生成：%s", output_path)
    return output_path
