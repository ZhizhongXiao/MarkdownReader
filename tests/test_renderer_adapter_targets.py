"""新 adapter 的 TARGET 七项套件：checkbox / mark / callout / wikilink / obsidian-tag /
mermaid / plantuml。

与 Phase 1 的 tests/test_markdown_compat_target.py 并存：那份门禁跑的是**旧生产 renderer**，
仍是 7 个 strict xfail；本模块不改变它，只证明新 adapter 已承担这七项语义（Phase 4A 五项 +
Phase 4C 两项；图表细节见 tests/test_renderer_adapter_diagrams.py）。

feature 必须来自 token 语义：本模块用 raw HTML 反例（<mark>、<input type=checkbox>、
<div class="callout">、<a class="obsidian-wikilink">、<span class="obsidian-tag">）证明
features 不会被 substring 误报。
"""

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from markdown_fixtures import load_cases, read_fixture  # noqa: E402
from renderer_adapter import render  # noqa: E402

MIGRATED = (
    "checkbox",
    "mark",
    "callout",
    "wikilink",
    "obsidian-tag",
    "mermaid",
    "plantuml",
)
# Phase 4C 起没有 pending：七项 TARGET 全部由新 adapter 承担。
PENDING: tuple[str, ...] = ()

# features 里的键名（注意 obsidian-tag 的键是 obsidian_tag）
MIGRATED_FEATURE_KEYS = ("checkbox", "mark", "callout", "wikilink", "obsidian_tag")

RAW_HTML_LOOKALIKES = (
    "<mark>raw</mark>\n\n"
    '<input type="checkbox">\n\n'
    '<div class="callout" data-callout="note">raw</div>\n\n'
    '<a class="obsidian-wikilink" href="#">raw</a>\n\n'
    '<span class="obsidian-tag">raw</span>\n'
)

ALL_FIVE_SYNTAXES = (
    "- [ ] 任务\n\n"
    "==高亮==\n\n"
    "> [!NOTE]\n> 提示。\n\n"
    "[[目标]]\n\n"
    "#标签\n"
)


def _case(case_id: str) -> dict:
    cases = {case["id"]: case for case in load_cases("target")}
    assert case_id in cases, case_id
    return cases[case_id]


def _render_case(case_id: str) -> dict:
    return render(read_fixture(_case(case_id)))


def test_target_coverage_is_locked():
    """7 个 target case 必须全部登记为已迁移，不留静默空缺。"""
    ids = sorted(case["id"] for case in load_cases("target"))

    assert sorted(MIGRATED + PENDING) == ids


def test_checkbox_uses_upstream_semantics():
    envelope = _render_case("checkbox")
    html = envelope["html"]

    assert html.count('type="checkbox"') == 2, html
    assert "checked" in html, "已勾选项必须带 checked"
    assert "[ ] 未完成事项" not in html and "[x] 已完成事项" not in html
    assert envelope["features"]["checkbox"] is True


def test_plain_list_is_not_a_task_list():
    envelope = render("- 无序一\n- 无序二\n")

    assert 'type="checkbox"' not in envelope["html"]
    assert envelope["features"]["checkbox"] is False


def test_mark_uses_upstream_semantics():
    envelope = _render_case("mark")
    html = envelope["html"]

    assert "<mark>" in html, html
    assert "==高亮文本==" not in html
    assert envelope["features"]["mark"] is True


def test_single_equals_text_is_not_mark():
    envelope = render("a = b 与 价格 == 5\n")

    assert "<mark" not in envelope["html"]
    assert envelope["features"]["mark"] is False


def test_callout_note_and_warning_both_recognised():
    envelope = _render_case("callout")
    html = envelope["html"]

    assert "[!NOTE]" not in html and "[!WARNING]" not in html
    assert "这是一个提示块。" in html and "这是一个警告块。" in html
    assert envelope["features"]["callout"] is True
    assert 'class="callout"' in html
    assert 'data-callout="note"' in html and 'data-callout="warning"' in html


def test_plain_blockquote_is_not_a_callout():
    envelope = render("> 普通引用。\n")

    assert "<blockquote>" in envelope["html"]
    assert 'class="callout"' not in envelope["html"]
    assert envelope["features"]["callout"] is False


def test_wikilink_static_export_keeps_target_and_alias():
    envelope = _render_case("wikilink")
    html = envelope["html"]

    assert envelope["features"]["wikilink"] is True
    assert '[[' not in html, "WikiLink 源标记不应残留"
    assert "第二章</a>" in html, "[[第二章]] 的可见文本必须是目标名"
    assert "别名显示</a>" in html, "alias 的可见文本必须是 alias"
    assert 'href="#"' not in html, "静态导出不能留下编辑器用的空 href"

    # 只取真正的 href 属性：data-href="…" 里的子串不算。
    hrefs = re.findall(r"\shref=\"([^\"]*)\"", html)
    assert len(hrefs) == 2, html
    for href in hrefs:
        assert href and href != "#", href
        assert "第二章" in unquote(href), href


def test_obsidian_tag_ascii_and_unicode():
    envelope = _render_case("obsidian-tag")
    html = envelope["html"]

    assert envelope["features"]["obsidian_tag"] is True
    assert "#笔记" in html and "#项目/子项" in html
    assert html.count('class="obsidian-tag"') == 2, html

    ascii_envelope = render("#note 与 #project/sub 与 #a_b。\n")
    assert ascii_envelope["features"]["obsidian_tag"] is True
    assert ascii_envelope["html"].count('class="obsidian-tag"') == 3


def test_obsidian_tag_ignores_headings_urls_and_bare_hash():
    envelope = render("# 标题\n\nhttps://example.com/page#section\n\n孤立 # 符号 与 #\n")

    assert envelope["features"]["obsidian_tag"] is False
    assert 'class="obsidian-tag"' not in envelope["html"]
    assert '<a href="https://example.com/page#section">' in envelope["html"]


def test_features_are_token_driven_not_substring():
    lookalikes = render(RAW_HTML_LOOKALIKES)
    for key in MIGRATED_FEATURE_KEYS:
        assert lookalikes["features"][key] is False, key

    real = render(ALL_FIVE_SYNTAXES)
    for key in MIGRATED_FEATURE_KEYS:
        assert real["features"][key] is True, key


def test_mermaid_and_plantuml_are_migrated():
    """Phase 4C：两项图表语义由 adapter 承担；runtime 与抓图仍属 Phase 5。"""
    mermaid = _render_case("mermaid")
    assert mermaid["features"]["mermaid"] is True
    assert 'class="mermaid"' in mermaid["html"]
    assert "mermaid.min.js" not in mermaid["html"]

    plantuml = _render_case("plantuml")
    assert plantuml["features"]["plantuml"] is True
    assert "<img" in plantuml["html"]


def test_heading_wikilink_stays_toc_safe_after_the_export_adaptation():
    envelope = render("# 参见 [[第二章]]\n")
    heading = envelope["headings"][0]

    assert "<" not in heading["toc_inline_html"], heading["toc_inline_html"]
    assert heading["toc_inline_html"] == "参见 第二章"
    assert "<a" in heading["inline_html"]

def test_obsidian_tag_mixed_candidates_are_not_truncated():
    """混合 tag 必须整段成为一个 tag。

    上游 ASCII rule 只会吃掉 ASCII 前缀（#abc）而把中文/路径留下；所以含 Unicode 的
    candidate 必须由 MarkdownReader compatibility rule 整段消费。
    """
    envelope = render("#abc中文 与 #abc/项目 与 #项目/sub。\n")
    html = envelope["html"]

    assert envelope["features"]["obsidian_tag"] is True
    assert html.count('class="obsidian-tag"') == 3, html
    for tag_text in ("#abc中文", "#abc/项目", "#项目/sub"):
        assert ">" + tag_text + "</span>" in html, tag_text
    assert ">#abc</span>中文" not in html, "ASCII 前缀被单独消费、中文残留"
    assert ">#abc</span>/项目" not in html, "ASCII 前缀被单独消费、路径残留"
