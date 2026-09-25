"""TARGET：本次升级要从 vscode-office 新增的 Markdown 语义（迁移门禁）。

Cutover C4 之后这 7 条由 production renderer（v2）真实保证，因此不再是 xfail：它们以普通
断言运行，一旦回归就直接失败。语料与检查函数依旧一一对应，条数锁定在
EXPECTED_TARGET_CASES；Final Acceptance 之前不允许出现 xfail 或 skip。

Phase 1 只锁产品级语义，不锁尚未 pin 住的上游 DOM：Phase 2 固定 vscode-office
commit、Phase 3 adapter 定型以后，再补确实需要的上游 DOM contract。
"""

import re
import sys
from html import unescape
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from markdown_fixtures import load_cases, render_fixture  # noqa: E402

EXPECTED_TARGET_CASES = 7

# Callout 的具体类名要等 Phase 2 pin 住上游后再收窄，这里只要求“可被识别为提示块”。
CALLOUT_MARKERS = ("callout", "admonition", "markdown-alert", "alert", "note")

# Obsidian 标签同理：类名或链接形式任一即可。
OBSIDIAN_TAG_MARKERS = ('class="tag', "tag-", "obsidian-tag", "/tags/", 'href="#tag')

# WikiLink 断言只要求“指向目标”：不锁精确 URL 格式，也不锁 DOM class。
_ANCHOR_RE = re.compile(r'<a\b[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _anchors(html: str) -> list[tuple[str, str]]:
    """返回 (href, 可见文本) 列表，可见文本已去标签。"""
    return [
        (match.group(1), _TAG_RE.sub("", match.group(2)).strip())
        for match in _ANCHOR_RE.finditer(html)
    ]


def _expect_checkbox(result: dict) -> None:
    """任务列表必须成为 checkbox 语义，而不是字面文本。"""
    html = result["html"]
    assert html.count('type="checkbox"') == 2, html
    assert "[ ] 未完成事项" not in html, html


def _expect_mark(result: dict) -> None:
    html = result["html"]
    assert "<mark>" in html, html
    assert "==高亮文本==" not in html, html


def _expect_callout(result: dict) -> None:
    """两个 marker 都必须消失：只做 NOTE 而把 WARNING 留成普通文本不算通过。"""
    html = result["html"]
    assert "[!NOTE]" not in html, html
    assert "[!WARNING]" not in html, html
    assert "这是一个提示块。" in html, html
    assert "这是一个警告块。" in html, html
    assert any(marker in html for marker in CALLOUT_MARKERS), html


def _expect_wikilink(result: dict) -> None:
    """链接不仅出现，还要指向目标：alias 显示别名，两点都指向「第二章」。"""
    html = result["html"]
    assert "[[" not in html, html

    labelled = {text: href for href, text in _anchors(html)}
    assert "第二章" in labelled, labelled
    assert "别名显示" in labelled, labelled
    for label in ("第二章", "别名显示"):
        href = labelled[label]
        assert href, (label, labelled)
        assert "第二章" in unquote(unescape(href)), (label, href)


def _expect_obsidian_tag(result: dict) -> None:
    html = result["html"]
    assert any(marker in html for marker in OBSIDIAN_TAG_MARKERS), html


def _expect_mermaid(result: dict) -> None:
    """Mermaid 必须被识别为图表，并由渲染器报告 feature（Phase 3 协议）。"""
    html = result["html"]
    assert result.get("features", {}).get("mermaid") is True, result.get("features")
    assert 'class="mermaid"' in html, html


def _expect_plantuml(result: dict) -> None:
    """PlantUML 必须进入网络图资源流程：内嵌图像或保留服务端 URL。"""
    html = result["html"]
    assert result.get("features", {}).get("plantuml") is True, result.get("features")
    assert "<img" in html, html


TARGET_CHECKS = {
    "checkbox": _expect_checkbox,
    "mark": _expect_mark,
    "callout": _expect_callout,
    "wikilink": _expect_wikilink,
    "obsidian-tag": _expect_obsidian_tag,
    "mermaid": _expect_mermaid,
    "plantuml": _expect_plantuml,
}


def _cases() -> dict[str, dict]:
    return {case["id"]: case for case in load_cases("target")}


def test_target_corpus_is_registered_and_locked():
    """语料与检查函数必须一一对应，条数锁定。"""
    cases = _cases()

    assert len(cases) == EXPECTED_TARGET_CASES
    assert sorted(cases) == sorted(TARGET_CHECKS)


def test_every_target_fixture_renders_today():
    """先证明语料真的都能渲染，再看下面每条语义断言：失败来自语义，不是崩溃或缺文件。"""
    for case_id, case in sorted(_cases().items()):
        result = render_fixture(case)
        assert result["html"].strip(), case_id
        assert isinstance(result["warnings"], list), case_id


@pytest.mark.parametrize("case_id", sorted(TARGET_CHECKS))
def test_target_case_is_implemented(case_id: str):
    TARGET_CHECKS[case_id](render_fixture(_cases()[case_id]))
