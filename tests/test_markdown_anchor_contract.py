"""KEEP：heading ↔ TOC 的关系契约（只锁链路，不锁 slug 文本）。

本模块锁的是“链路不断”：id 非空唯一、metadata anchor 与正文 id 一致、TOC data-id
与正文 id 一致、href 能解析回同一个 heading。它刻意不断言中文/emoji/标点的精确
slug，也不断言重复标题用 -2、空标题用 _1——那些是今天的实现输出，Phase 4 允许按
vscode-office / markdown-it-anchor 对齐；今天的精确值只作为诊断记录在
docs/MARKDOWN_COMPATIBILITY.md 的 TRANSITIONAL T5 一行。

正文与目录取自 converter.process_single 生成的真实文档产物；metadata 由渲染器
返回，是 core/toc.py 与 Viewer 的共同来源。
"""

import re
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from markdown_fixtures import fixture_path, load_cases, render_fixture  # noqa: E402

import core.converter as converter  # noqa: E402

EXPECTED_ANCHOR_CASES = 1
EXPECTED_ANCHOR_HEADINGS = 8

BODY_HEADING_RE = re.compile(r'<h([1-6])\s+id="([^"]+)"')
TOC_ROW_RE = re.compile(r'<div class="toc-row" data-id="([^"]+)"')
TOC_LINK_RE = re.compile(r'<a class="toc-link" href="#([^"]+)"')

CONFIG = {"template": "modern", "numbering": False, "overwrite": True}


@pytest.fixture(scope="module")
def anchor_case() -> dict:
    cases = load_cases("anchor")
    assert len(cases) == EXPECTED_ANCHOR_CASES
    return cases[0]


@pytest.fixture(scope="module")
def rendered(anchor_case: dict) -> dict:
    return render_fixture(anchor_case)


@pytest.fixture(scope="module")
def document_html(anchor_case: dict, tmp_path_factory) -> str:
    """把锚点语料转换成真实文档，返回生成的 HTML。"""
    output = tmp_path_factory.mktemp("anchor") / "anchor-relationship.html"
    saved = converter.process_single(str(fixture_path(anchor_case)), str(output), CONFIG)
    assert saved == str(output)
    return output.read_text(encoding="utf-8")


def _body_heading_ids(html: str) -> list[str]:
    return [match.group(2) for match in BODY_HEADING_RE.finditer(html)]


def test_anchor_corpus_is_registered_once(anchor_case: dict):
    assert anchor_case["group"] == "anchor"
    assert fixture_path(anchor_case).is_file()


def test_every_heading_gets_a_unique_non_empty_id(rendered: dict):
    anchors = [heading["anchor"] for heading in rendered["headings"]]
    body_ids = _body_heading_ids(rendered["html"])

    assert len(anchors) == EXPECTED_ANCHOR_HEADINGS
    assert all(anchors), "每个 heading 都必须有非空 id"
    assert len(set(anchors)) == len(anchors), "id 必须唯一"
    assert sorted(anchors) == sorted(body_ids), "正文 heading 的 id 必须与 metadata 一一对应"


def test_heading_metadata_matches_the_body_headings(rendered: dict):
    body = [
        (int(match.group(1)), match.group(2))
        for match in BODY_HEADING_RE.finditer(rendered["html"])
    ]
    metadata = [(heading["level"], heading["anchor"]) for heading in rendered["headings"]]

    assert metadata == body, "level 与 id 必须按顺序一致（metadata 是 TOC 与 Viewer 的来源）"


def test_heading_levels_and_texts_are_reported(rendered: dict):
    assert [heading["level"] for heading in rendered["headings"]] == [1, 2, 3, 2, 2, 2, 2, 2]
    assert [heading["text"] for heading in rendered["headings"]] == [
        "中文标题",
        "带标点的标题，！？（）",
        "🚀 Emoji 标题",
        "中文标题",
        "🚀 Emoji 标题",
        "",
        "A",
        "标题的收尾",
    ]


def test_fenced_code_never_contributes_headings(rendered: dict):
    texts = [heading["text"] for heading in rendered["headings"]]

    assert "围栏里的标题" not in texts
    assert "# 围栏里的标题" in rendered["html"], "围栏内容必须作为代码文本保留"


def test_trailing_hashes_are_not_part_of_the_heading_text(rendered: dict):
    assert all("#" not in heading["text"] for heading in rendered["headings"])
    assert rendered["headings"][-1]["text"] == "标题的收尾"


def test_duplicate_headings_get_distinct_ids(rendered: dict):
    anchors = [heading["anchor"] for heading in rendered["headings"]]
    texts = [heading["text"] for heading in rendered["headings"]]

    for duplicated in ("中文标题", "🚀 Emoji 标题"):
        indexes = [index for index, text in enumerate(texts) if text == duplicated]
        assert len(indexes) == 2, duplicated
        assert anchors[indexes[0]] != anchors[indexes[1]], duplicated


def test_toc_rows_link_back_to_the_body_headings(document_html: str):
    body_ids = _body_heading_ids(document_html)
    toc_ids = TOC_ROW_RE.findall(document_html)
    link_targets = TOC_LINK_RE.findall(document_html)

    assert len(toc_ids) == len(body_ids) == EXPECTED_ANCHOR_HEADINGS
    assert toc_ids == body_ids, "TOC 的 data-id 必须与正文 heading id 一致"
    assert [unquote(target) for target in link_targets] == body_ids, (
        "每个 TOC 链接都必须指向对应 heading"
    )
