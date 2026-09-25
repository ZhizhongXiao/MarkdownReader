"""新 adapter 的 Phase 4C 图表套件：Mermaid recognition/容器 + PlantUML 语义。

范围只到「Markdown → 图表语义 HTML → feature」：

  * Mermaid：recognition 由 pinned vscode-office 语义决定（predicate 的唯一来源是
    renderer/extensions/mermaid_export.js），容器内容按 D2 escape，**不做语法校验**；
  * PlantUML：token 与 URL 由 markdown-it-plantuml@^1.4.1 生成，只构造 server URL，不访问网络。

runtime 注入、抓图、内嵌、data URI 全部属于 Phase 5，本套件对它们有显式断言（本模块完全离线）。
旧 production renderer 两项都不支持，因此这里没有 old/new 对照（见 semantic parity 套件的 scope）。
PlantUML 围栏契约只覆盖「body 内含 @startuml/@enduml」的写法；缺标记的 body 未定义，
本套件刻意不锁定。
"""

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from markdown_fixtures import load_cases, read_fixture  # noqa: E402
from renderer_adapter import render  # noqa: E402

# 与 renderer/extensions/plantuml_export.js 的 DEFAULT_PLANTUML_SERVER 一致（也与插件默认值一致）。
DEFAULT_PLANTUML_SERVER = "https://www.plantuml.com/plantuml"
CUSTOM_PLANTUML_SERVER = "https://plantuml.example.invalid/plantuml"


def _case(group: str, case_id: str) -> dict:
    cases = {case["id"]: case for case in load_cases(group)}
    assert case_id in cases, case_id
    return cases[case_id]


def _mermaid(markdown: str, options: dict | None = None) -> dict:
    return render(markdown, options=options)


def _img_src(html: str) -> str:
    match = re.search(r'<img[^>]*src="([^"]+)"', html)
    assert match, html
    return match.group(1)


class _ContainerReader(HTMLParser):
    """读取 class="mermaid" 容器的 DOM 文本，并记录容器内出现过的元素。

    转义正确时，容器内只应有文本（inner_elements 为空），文本应等于作者原文。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.inside = False
        self.chunks: list[str] = []
        self.inner_elements: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.inside and dict(attrs).get("class") == "mermaid":
            self.inside = True
            return
        if self.inside:
            self.inner_elements.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.inside and tag == "div":
            self.inside = False

    def handle_data(self, data: str) -> None:
        if self.inside:
            self.chunks.append(data)


def _container_text(html: str) -> tuple[str, list[str]]:
    reader = _ContainerReader()
    reader.feed(html)
    return "".join(reader.chunks), reader.inner_elements

# --- Mermaid：recognition + 容器（Phase 4C 不做校验） ----------------------


def test_mermaid_target_fixture_becomes_a_source_container():
    envelope = render(read_fixture(_case("target", "mermaid")))
    html = envelope["html"]

    assert envelope["features"]["mermaid"] is True
    assert '<div class="mermaid">' in html
    text, elements = _container_text(html)
    assert elements == []
    assert text == "graph TD\n  A[开始] --> B[结束]"


def test_implicit_recognition_follows_pinned_upstream():
    """上游按首行自动识别：gantt / sequenceDiagram / graph TB|BT|RL|LR|TD（可带尾随分号）。"""
    for first_line in ("gantt\ntitle x", "sequenceDiagram\nA->>B: hi", "graph LR;\nA-->B"):
        envelope = _mermaid("```\n" + first_line + "\n```\n")

        assert envelope["features"]["mermaid"] is True, first_line
        assert '<div class="mermaid">' in envelope["html"], first_line


@pytest.mark.parametrize(
    "first_line",
    [
        "flowchart TB\nA-->B",
        "graph lr\nA-->B",
        "sequenceDiagram;",
        "graph LR; extra",
        "const a = 1;",
    ],
)
def test_ordinary_fences_stay_code_blocks(first_line: str):
    envelope = _mermaid("```\n" + first_line + "\n```\n")
    html = envelope["html"]

    assert envelope["features"]["mermaid"] is False
    assert '<div class="mermaid">' not in html
    assert "<pre><code>" in html


def test_a_fence_language_does_not_prevent_recognition():
    """上游 quirk（复刻而非修正）：只看内容首行，不看语言标记。"""
    envelope = _mermaid("```js\ngantt\ntitle x\n```\n")

    assert envelope["features"]["mermaid"] is True
    assert '<div class="mermaid">' in envelope["html"]


def test_raw_html_mermaid_lookalike_is_not_a_feature():
    envelope = render('<div class="mermaid">graph TD</div>\n')

    assert '<div class="mermaid">' in envelope["html"], "raw HTML 原样保留"
    assert envelope["features"]["mermaid"] is False, "raw HTML 不得让 feature 误报"


def test_invalid_mermaid_is_not_validated_in_phase4c():
    """Phase 4C 契约：识别成 Mermaid 就保留 source 容器，不校验语法，也不允许崩溃。"""
    envelope = _mermaid("```mermaid\nthis is not a diagram\n```\n")
    text, elements = _container_text(envelope["html"])

    assert envelope["features"]["mermaid"] is True
    assert envelope["warnings"] == []
    assert elements == []
    assert text == "this is not a diagram"


def test_mermaid_container_keeps_the_runtime_out_of_the_html():
    """5B 登记改写：runtime 由 resources.scripts 交付，adapter 不自己注入脚本。

    4C 时的断言是「html 里完全没有 runtime」；5B 起 Mermaid 文档会**通过资源通道**交付 vendored
    runtime（按需，AGENTS §9），但页面装配仍属 assembler，因此 html 依旧没有任何 <script>。
    """
    envelope = _mermaid("```mermaid\ngraph LR\nA --> B\n```\n")
    html = envelope["html"]

    assert "<script" not in html
    assert "mermaid.min.js" not in html
    assert "mermaid.initialize" not in html and "mermaid.run" not in html
    assert "cdn" not in html.lower()
    assert [script["id"] for script in envelope["resources"]["scripts"]] == ["mermaid"], (
        "runtime 只走资源通道"
    )


def test_mermaid_container_escapes_but_round_trips_the_author_source():
    """D2 不变式：serialization 转义成惰性文本，但交给 runtime 的 DOM 文本等于作者原文。"""
    source = 'A["<b>x</b> & y"] --> B'
    html = _mermaid("```mermaid\n" + source + "\n```\n")["html"]

    assert "&lt;b&gt;" in html and "&amp;" in html, "HTML transport 必须转义"
    text, elements = _container_text(html)
    assert elements == [], "转义失败：容器内出现了元素"
    assert text == source


def test_mermaid_container_preserves_author_entities():
    """作者写 &amp;：上游未转义时浏览器会先解码；本 adapter 必须保持作者原文。"""
    html = _mermaid('```mermaid\ngraph TD\nA["a &amp; b"]\n```\n')["html"]

    text, _ = _container_text(html)
    assert text == 'graph TD\nA["a &amp; b"]'


def test_the_adapter_does_not_depend_on_the_mermaid_package():
    """4C 边界：renderer production dependencies 不含 mermaid，adapter 也不 import 它。"""
    manifest = json.loads((ROOT / "renderer" / "package.json").read_text(encoding="utf-8"))
    assert "mermaid" not in manifest["dependencies"]

    source = (ROOT / "renderer" / "extensions" / "mermaid_export.js").read_text(encoding="utf-8")
    assert 'require("mermaid")' not in source
    assert 'from "mermaid"' not in source
# --- PlantUML：插件 token / URL（完全离线） --------------------------------


def test_plantuml_target_fixture_produces_an_image():
    envelope = render(read_fixture(_case("target", "plantuml")))
    html = envelope["html"]

    assert envelope["features"]["plantuml"] is True
    assert "<img" in html
    assert _img_src(html).startswith(DEFAULT_PLANTUML_SERVER + "/svg/")


def test_plantuml_bare_block_produces_an_image():
    """pinned 上游导出路径的原始形式：裸 @startuml 块（markdown-it-plantuml 的语义）。"""
    envelope = render("@startuml\nAlice -> Bob: Hello\n@enduml\n")

    assert envelope["features"]["plantuml"] is True
    assert '<img src="' + DEFAULT_PLANTUML_SERVER + "/svg/" in envelope["html"]


def test_plantuml_url_matches_the_plugin_default_formula():
    """golden：Phase 4C characterization 记录的插件默认公式结果（离线，不访问 URL）。"""
    envelope = render("@startuml\nAlice -> Bob: Hello\n@enduml\n")

    assert _img_src(envelope["html"]) == (
        DEFAULT_PLANTUML_SERVER + "/svg/SoWkIImgAStDuNBCoKnELT2rKt3AJx9Iy4ZDoSddSaZDIm7A0G00"
    )


def test_plantuml_url_is_deterministic_for_the_same_source():
    bare = "@startuml\nA -> B\n@enduml\n"
    fenced = "```plantuml\n" + bare + "```\n"

    assert _img_src(render(bare)["html"]) == _img_src(render(bare)["html"])
    assert _img_src(render(fenced)["html"]) == _img_src(render(fenced)["html"])


def test_plantuml_server_is_configurable():
    envelope = render(
        "@startuml\nA -> B\n@enduml\n", options={"plantuml_server": CUSTOM_PLANTUML_SERVER}
    )
    source = _img_src(envelope["html"])

    assert source.startswith(CUSTOM_PLANTUML_SERVER + "/svg/")
    assert DEFAULT_PLANTUML_SERVER not in source, "自定义 server 必须完全取代默认值"
    assert envelope["warnings"] == [], "构造 URL 不产生 warning，也不访问网络"


def test_plantuml_fence_language_variants_are_supported():
    for language in ("plantuml", "puml"):
        envelope = render("```" + language + "\n@startuml\nA -> B\n@enduml\n```\n")

        assert envelope["features"]["plantuml"] is True, language
        assert "<img" in envelope["html"], language


def test_plantuml_unclosed_block_is_autoclosed():
    """插件语义：没有 @enduml 时按父容器结束自动闭合，仍然是 diagram。"""
    envelope = render("@startuml\nAlice -> Bob: Hello\n")

    assert envelope["features"]["plantuml"] is True
    assert "<img" in envelope["html"]


def test_plantuml_alt_text_follows_the_plugin_semantics():
    envelope = render("@startuml 图例标题\nA -> B\n@enduml\n")

    assert 'alt="图例标题"' in envelope["html"]


def test_non_plantuml_text_is_left_alone():
    """不在行首的 @startuml 不是 diagram（插件 grammar），文本原样保留。"""
    envelope = render("说明：@startuml 必须出现在行首。\n")

    assert envelope["features"]["plantuml"] is False
    assert "<img" not in envelope["html"]
    assert "@startuml" in envelope["html"]


def test_raw_html_plantuml_lookalike_is_not_a_feature():
    envelope = render('<img src="https://www.plantuml.com/plantuml/svg/example">\n')

    assert "<img" in envelope["html"], "raw HTML 原样保留"
    assert envelope["features"]["plantuml"] is False, "raw HTML 不得让 feature 误报"


def test_plantuml_rendering_keeps_the_url_when_fetching_is_disabled():
    """Phase 5C 登记改写：PlantUML 抓图由 `fetch_remote_resources` 控制。

    本用例（harness 默认关闭抓取）锁「不联网、URL 原样、无 warning、无 data URI」；
    联网成功 → data URI、失败 → 原 URL + warning + 转换继续，由 tests/test_renderer_network.py
    用 127.0.0.1 loopback 服务器证明（G7 的资源部分）。
    """
    options = {"plantuml_server": CUSTOM_PLANTUML_SERVER}
    envelope = render("@startuml\nA -> B\n@enduml\n", options=options)
    html = envelope["html"]

    assert "data:image" not in html and "base64" not in html
    assert "<script" not in html
    assert _img_src(html).startswith(CUSTOM_PLANTUML_SERVER + "/svg/"), "URL 必须原样保留"
    (item,) = [entry for entry in envelope["resources"]["items"] if entry["kind"] == "plantuml"]
    assert item["source"] == "remote" and item["status"] == "kept", item
    assert envelope["warnings"] == []


def test_plantuml_fence_feature_is_token_driven():
    """feature 来自插件 token，而不是 HTML substring：单独出现 <img> 的文档不得误报。"""
    envelope = render("普通图片：![图](diagram.png)\n")

    assert "<img" in envelope["html"]
    assert envelope["features"]["plantuml"] is False


def test_the_adapter_keeps_the_pinned_plugin_version():
    manifest = json.loads((ROOT / "renderer" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "renderer" / "package-lock.json").read_text(encoding="utf-8"))
    installed = lock["packages"]["node_modules/markdown-it-plantuml"]["version"]

    assert manifest["dependencies"]["markdown-it-plantuml"] == "^1.4.1"
    assert installed == "1.4.1", "与 pinned vscode-office 的 ^1.4.1 不一致"
