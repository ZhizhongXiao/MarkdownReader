"""新 renderer 与 Phase 1 KEEP 语料的语义对照（Phase 3）。

不要求新旧 HTML 字节一致，只按语义断言（期望表直接复用 Phase 1 的 KEEP_EXPECTATIONS）。
每个 KEEP case 必须被显式分类：

  * ADAPTER_CASES —— 新 adapter 已负责，逐条对照；
  * PENDING_CASES  —— Phase 3 尚未迁移，写明理由；不伪造通过、不改 Phase 1 契约。

分类表由测试锁定：出现未分类的 case 即失败，避免静默缩小对照范围。
Phase 1 的 7 个 TARGET xfail 属于旧 renderer 的门禁，本阶段不改动它们。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from markdown_fixtures import load_cases, read_fixture  # noqa: E402
from renderer_adapter import render  # noqa: E402
from test_markdown_compat_keep import KEEP_EXPECTATIONS  # noqa: E402

EXPECTED_KEEP_CASES = 15

ADAPTER_CASES = (
    "inline-basic",
    "paragraph-breaks-off",
    "typographer-off",
    "heading-levels",
    "heading-trailing-hash",
    "code-fence-heading-text",
    "table-alignment",
    "code-fence-language",
    "blockquote-and-hr",
    "list-nested",
    "raw-inline-html",
    "link-and-autolink",
    "math-inline-display",
    "plain-text-no-math",
)

PENDING_CASES = {
    "footnote": (
        "上游 pinned commit 没有 footnote 实现；作为 MarkdownReader-owned extension"
        " 在 Phase 4 迁移，Phase 1 的 KEEP 契约保持不变。"
    ),
}

# Phase 4A 已接入 checkbox / mark / callout（证据在 tests/test_renderer_adapter_targets.py）；
# 这里只保留仍然 pending 的项：Phase 4C/5 完成前它们必须恒为 false。
PENDING_FEATURE_KEYS = ("mermaid", "plantuml")


def _case(case_id: str) -> dict:
    cases = {case["id"]: case for case in load_cases("keep")}
    assert case_id in cases, case_id
    return cases[case_id]


def test_keep_coverage_table_is_complete_and_locked():
    case_ids = sorted(case["id"] for case in load_cases("keep"))
    covered = sorted(ADAPTER_CASES)
    pending = sorted(PENDING_CASES)

    assert len(case_ids) == EXPECTED_KEEP_CASES
    assert sorted(covered + pending) == case_ids, (covered, pending)
    assert all(PENDING_CASES.values()), "pending 必须写明理由"
    assert all(case_id in KEEP_EXPECTATIONS for case_id in covered), "对照必须复用 Phase 1 的期望表"


@pytest.mark.parametrize("case_id", ADAPTER_CASES)
def test_adapter_satisfies_covered_keep_case(case_id: str):
    envelope = render(read_fixture(_case(case_id)))
    html = envelope["html"]
    expected = KEEP_EXPECTATIONS[case_id]

    for fragment in expected.get("must_contain", []):
        assert fragment in html, (case_id, fragment)
    for alternatives in expected.get("must_contain_any", []):
        assert any(option in html for option in alternatives), (case_id, alternatives)
    for fragment in expected.get("must_absent", []):
        assert fragment not in html, (case_id, fragment)
    if "headings_levels" in expected:
        levels = [item["level"] for item in envelope["headings"]]
        assert levels == expected["headings_levels"], case_id
    if "headings_texts" in expected:
        texts = [item["text"] for item in envelope["headings"]]
        assert texts == expected["headings_texts"], case_id


def test_heading_relationship_contract_holds_for_the_anchor_fixture():
    """K14 的关系契约：只锁「链路不断」，不锁精确 slug 文本。"""
    anchor_cases = load_cases("anchor")
    assert len(anchor_cases) == 1
    envelope = render(read_fixture(anchor_cases[0]))
    html = envelope["html"]
    headings = envelope["headings"]

    anchors = [item["anchor"] for item in headings]
    assert len(anchors) == 8
    assert all(anchors), "每个 heading 都必须有非空 id"
    assert len(set(anchors)) == len(anchors), "id 必须唯一"
    for heading in headings:
        assert 'id="' + heading["anchor"] + '"' in html, heading["anchor"]
    assert [item["level"] for item in headings] == [1, 2, 3, 2, 2, 2, 2, 2]
    assert "围栏里的标题" not in [item["text"] for item in headings]


def test_pending_features_stay_off_in_phase4a():
    """Phase 4A 只迁移了五项；mermaid / plantuml 在 Phase 4C/5 之前必须仍然关闭。"""
    for case in sorted(load_cases("target"), key=lambda item: item["id"]):
        features = render(read_fixture(case))["features"]
        for key in PENDING_FEATURE_KEYS:
            assert features[key] is False, (case["id"], key)

# K14 回归：TOC-safe 表示。正文 inline_html 保留链接，TOC metadata 只保留可见、非交互内容。
LINK_SAFE_DOCUMENT = (
    "# 普通 [链接](https://example.com)\n"
    "\n"
    "# Wiki [[第二章]]\n"
    "\n"
    "# 别名 [[第二章|别名显示]]\n"
    "\n"
    "# 嵌入 ![[图]]\n"
    "\n"
    "# 原始 <a href=\"https://x\">raw</a> 与 ![图](x.png)\n"
)


def test_toc_inline_metadata_never_embeds_links():
    """TOC 标题可以保留行内格式，但链接必须降级为可见文本。

    上游 obsidian 扩展的 wikilink / wikilink_embed 是自定义 token，其 renderer 会产出
    <a> / <span data-href>；放进 TOC 导航链接会形成 nested anchor，因此 TOC 版本只保留
    可见、非交互内容。
    """
    headings = render(LINK_SAFE_DOCUMENT)["headings"]
    toc_texts = [heading["toc_inline_html"] for heading in headings]

    assert len(headings) == 5
    assert all("<" not in text for text in toc_texts), toc_texts
    assert toc_texts == [
        "普通 链接",
        "Wiki 第二章",
        "别名 别名显示",
        "嵌入 图",
        "原始 raw 与 图",
    ]


def test_body_inline_html_keeps_links_and_anchors_stay_sound():
    """TOC 侧降级不得影响正文 inline_html，也不得破坏 heading anchor 关系。"""
    envelope = render(LINK_SAFE_DOCUMENT)
    body = [heading["inline_html"] for heading in envelope["headings"]]
    anchors = [heading["anchor"] for heading in envelope["headings"]]

    assert "<a" in body[0] and "链接" in body[0]
    assert "<a" in body[1] and "第二章" in body[1]
    assert "别名显示" in body[2]
    assert "<" in body[3] and "图" in body[3]
    assert "<img" in body[4]

    assert all(anchors)
    assert len(set(anchors)) == len(anchors)
    for heading in envelope["headings"]:
        assert 'id="' + heading["anchor"] + '"' in envelope["html"], heading["anchor"]
