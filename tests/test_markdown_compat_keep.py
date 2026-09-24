"""KEEP：所有权将交给 vscode-office、但语义必须保持的 Markdown 语法。

分类与来源见 docs/MARKDOWN_COMPATIBILITY.md。语料只覆盖“今天仅由 demo 快照隐式
覆盖”的语法：本地图片、跨文档 .md 链接、front matter 已有各自专门的测试模块，矩阵
里登记为已覆盖，这里不重复造语料。

断言只使用 docs/MARKDOWN.md 描述的产品语义。凡文档没有固定标签形式的（例如删除线
渲染成 <s> 还是 <del>），断言接受任一等价形式，不冻结渲染器实现。

资产载荷契约（有公式才携带 KaTeX 资产、无公式不携带）不由本语料承担：它由现有的
tests/test_renderer_katex_assets.py 与 tests/test_converter_integration.py 锁定；语料只
断言 Markdown 语义（有公式得到 KaTeX HTML、无公式不出现公式标记）。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from markdown_fixtures import load_cases, render_fixture  # noqa: E402

# 锁定条数：manifest 少一个 case，或期望表少一条，都在这里失败，而不是让覆盖面积
# 悄悄变小。
EXPECTED_KEEP_CASES = 15

# 支持的期望键：
#   must_contain       html 中必须出现的片段
#   must_contain_any   每组至少出现一个（用于文档未固定具体标签的等价形式）
#   must_absent        html 中不得出现的片段
#   headings_levels    headings[].level 的完整序列
#   headings_texts     headings[].text 的完整序列
#   source             期望值的来源（文档或既有契约）
ASSERTION_KEYS = (
    "must_contain",
    "must_contain_any",
    "must_absent",
    "headings_levels",
    "headings_texts",
)

KEEP_EXPECTATIONS: dict[str, dict] = {
    "inline-basic": {
        "must_contain": [
            "<strong>粗体</strong>",
            "<em>斜体</em>",
            "<code>code</code>",
            "*保持字面*",
            "a &lt; b &amp; c",
        ],
        "must_contain_any": [["<s>删除线</s>", "<del>删除线</del>"]],
        "must_absent": ["<em>保持字面</em>"],
        "source": "MARKDOWN.md『行内』：粗体、斜体、删除线、行内代码、反斜杠转义",
    },
    "paragraph-breaks-off": {
        "must_contain": ["<p>第一行\n第二行</p>", "<p>空行分段。</p>"],
        "must_absent": ["<br"],
        "source": "MARKDOWN.md『解析器与选项』：breaks:false，单个换行不产生 <br>",
    },
    "typographer-off": {
        "must_contain": ["a -- b", "a ... b", "'single'"],
        "must_absent": ["“", "”", "‘", "’", "–", "—", "…"],
        "source": "MARKDOWN.md『解析器与选项』：typographer:false，不替换引号与破折号",
    },
    "heading-levels": {
        "must_contain": ["<h1 id=", "<h6 id="],
        "headings_levels": [1, 2, 3, 4, 5, 6],
        "headings_texts": ["一级标题", "二级标题", "三级标题", "四级标题", "五级标题", "六级标题"],
        "source": "MARKDOWN.md『标题』：H1–H6 生成锚点",
    },
    "heading-trailing-hash": {
        "must_contain": [">带尾随井号的标题</h2>"],
        "must_absent": ["井号的标题 #"],
        "headings_texts": ["带尾随井号的标题", "没有尾随井号"],
        "source": "MARKDOWN.md『标题』：ATX 收尾 # 不属于标题文本",
    },
    "code-fence-heading-text": {
        "must_contain": ['class="language-md"', "# 围栏里的标题"],
        "headings_texts": ["真正的标题"],
        "source": "MARKDOWN.md『代码』：围栏内不做公式或链接处理",
    },
    "table-alignment": {
        "must_contain": [
            "<thead>",
            "<tbody>",
            "text-align:left",
            "text-align:center",
            "text-align:right",
        ],
        "source": "MARKDOWN.md『列表与表格』：GFM 表格与列对齐",
    },
    "code-fence-language": {
        "must_contain": ['class="language-python"', "def hello():"],
        "source": "MARKDOWN.md『代码』：围栏代码块的语言标注保留",
    },
    "blockquote-and-hr": {
        "must_contain": ["<blockquote>", "<hr>", "引用第二行"],
        "source": "MARKDOWN.md『引用与分隔线』",
    },
    "list-nested": {
        "must_contain": ["<ol>", "<ul>", "嵌套项"],
        "source": "MARKDOWN.md『列表与表格』：有序、无序与嵌套列表",
    },
    "raw-inline-html": {
        "must_contain": [
            "<mark>raw mark</mark>",
            '<span style="color:#5b7fd4">',
            "<details>",
            "<summary>展开查看</summary>",
            "块级内容",
        ],
        "source": "MARKDOWN.md『原始 HTML』：行内与块级 HTML 原样保留",
    },
    "link-and-autolink": {
        "must_contain": [
            'href="https://example.com/a"',
            ">示例站点</a>",
            '<a href="https://example.com/b">',
            '<a href="https://example.com/c">',
        ],
        "source": "MARKDOWN.md『链接与图片』：标准链接、自动链接与裸 URL",
    },
    "footnote": {
        "must_contain": [
            'class="footnote-ref"',
            'class="footnotes"',
            'class="footnote-backref"',
        ],
        "must_absent": ["[^note]"],
        "source": "MARKDOWN.md『脚注』：引用、脚注区块与返回链接",
    },
    "math-inline-display": {
        "must_contain": ['class="katex"', 'class="katex-display"'],
        "source": "MARKDOWN.md『公式』：公式由 KaTeX 预渲染"
        "（载荷契约见 test_renderer_katex_assets.py）",
    },
    "plain-text-no-math": {
        "must_absent": ['class="katex', "mermaid", "plantuml"],
        "source": "MARKDOWN.md『公式』与 AGENTS §9：无公式的文档不出现公式标记"
        "（载荷契约见 test_renderer_katex_assets.py）",
    },
}


def _cases() -> dict[str, dict]:
    return {case["id"]: case for case in load_cases("keep")}


def test_keep_corpus_is_registered_and_fully_described():
    """语料与期望表必须一一对应，且每条都写明来源。"""
    cases = _cases()

    assert len(cases) == EXPECTED_KEEP_CASES
    assert sorted(cases) == sorted(KEEP_EXPECTATIONS)
    for case_id, expected in KEEP_EXPECTATIONS.items():
        assert expected.get("source"), case_id
        assert any(key in expected for key in ASSERTION_KEYS), case_id


@pytest.mark.parametrize("case_id", sorted(KEEP_EXPECTATIONS))
def test_keep_case_keeps_its_documented_markdown_semantics(case_id: str):
    result = render_fixture(_cases()[case_id])
    html = result["html"]
    expected = KEEP_EXPECTATIONS[case_id]

    for fragment in expected.get("must_contain", []):
        assert fragment in html, (case_id, fragment)
    for alternatives in expected.get("must_contain_any", []):
        assert any(option in html for option in alternatives), (case_id, alternatives)
    for fragment in expected.get("must_absent", []):
        assert fragment not in html, (case_id, fragment)
    if "headings_levels" in expected:
        levels = [heading["level"] for heading in result["headings"]]
        assert levels == expected["headings_levels"], case_id
    if "headings_texts" in expected:
        texts = [heading["text"] for heading in result["headings"]]
        assert texts == expected["headings_texts"], case_id
