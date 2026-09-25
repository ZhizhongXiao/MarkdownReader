"""Cutover C1：作者 raw HTML provenance 通道（`resources.author_references`）。

两侧共用 `tests/fixtures/author_references.json`：
  - 本文件通过**真实 dist** 渲染（`raw_fragments` 以单行 Markdown 送入，
    `documents` 直接是 Markdown）
  - `renderer/test/author_references.test.js` 在 node 侧跑同一批 fixture
    （scanner 直测 + dist 端到端）

C1 要证明的三件事：

  1. 通道只记录**作者 raw HTML**：Markdown 图片绝不出现（那是资源层 `items`），K13 边界未扩大；
  2. 形状契约：每 ref 一条、`count >= 1`、首次出现顺序、普通文档为 `[]`、协议仍 v2；
  3. closure checker 可以直接消费它（无需人工声明），raw HTML 文档得到 `author_references`
     而不是 `failure`。
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from renderer_adapter import render  # noqa: E402
from standalone_closure import assemble_and_scan, author_refs_from_envelope  # noqa: E402

FIXTURES = json.loads(
    (ROOT / "tests" / "fixtures" / "author_references.json").read_text(encoding="utf-8")
)
RAW_FRAGMENTS = FIXTURES["raw_fragments"]
DOCUMENTS = FIXTURES["documents"]


def channel(envelope: dict) -> list:
    return envelope["resources"]["author_references"]


@pytest.mark.parametrize("case", RAW_FRAGMENTS, ids=[case["name"] for case in RAW_FRAGMENTS])
def test_raw_html_fragments_report_exactly_the_expected_references(case):
    envelope = render(case["raw"] + "\n")

    assert channel(envelope) == case["expected"]


@pytest.mark.parametrize("case", DOCUMENTS, ids=[case["name"] for case in DOCUMENTS])
def test_document_fixtures_report_exactly_the_expected_references(case):
    envelope = render(case["markdown"])

    assert channel(envelope) == case["expected"]


def test_a_markdown_image_never_enters_the_provenance_channel():
    """通道只表达作者 raw HTML；Markdown 图片归资源层 items。"""
    envelope = render("![图](https://md.invalid/a.png)\n", {"fetch_remote_resources": False})

    assert channel(envelope) == []
    assert [item["kind"] for item in envelope["resources"]["items"]] == ["image"]


def test_raw_html_never_enters_the_resource_manifest():
    envelope = render('<img src="https://raw.invalid/a.png">\n')

    assert envelope["resources"]["items"] == [], "raw HTML 不进入资源层（K13）"
    assert channel(envelope) == [{"ref": "https://raw.invalid/a.png", "count": 1}]


def test_occurrences_are_counted_and_ordered_by_first_appearance():
    markdown = (
        '<img src="https://o.invalid/1.png">\n\n'
        '两处 <img src="https://o.invalid/2.png"> 与 <img src="https://o.invalid/1.png">\n'
    )

    assert channel(render(markdown)) == [
        {"ref": "https://o.invalid/1.png", "count": 2},
        {"ref": "https://o.invalid/2.png", "count": 1},
    ]


def test_the_checker_consumes_the_channel_without_manual_declarations():
    """端到端：作者 raw HTML 文档的 verdict 必须是 author_references，而不是 failure。"""
    result = assemble_and_scan('<img src="https://raw.invalid/a.png">\n')

    report = result["report"]
    assert author_refs_from_envelope(result["envelope"]) == [
        {"ref": "https://raw.invalid/a.png", "count": 1}
    ]
    assert report["verdict"] == "author_references", report["problems"]
    assert report["problems"] == []
    assert report["unexplained_external_resources"] == []


def test_a_url_shared_by_raw_html_and_a_kept_markdown_image_splits_the_buckets():
    """同 URL 两个来源：Markdown 那处 kept + 作者那处 → degraded 1 + author 1。"""
    url = "https://shared.invalid/a.png"
    markdown = '<img src="' + url + '">\n\n![图](' + url + ')\n'

    result = assemble_and_scan(markdown, {"fetch_remote_resources": False})

    report = result["report"]
    assert author_refs_from_envelope(result["envelope"]) == [{"ref": url, "count": 1}]
    assert report["verdict"] == "degraded", report["problems"]
    assert report["degraded_resources"][0]["occurrences"] == 1
    assert report["author_references"][0]["occurrences"] == 1
    assert report["unexplained_external_resources"] == []
