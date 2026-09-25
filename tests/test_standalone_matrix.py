"""Phase 5D 的可执行 closure matrix：真实 adapter → 真实 assembler → closure checker。

与 `test_renderer_network.py` 同一约定：只有 127.0.0.1 loopback 上的远程场景才真的联网，
其余用例不碰网络。远程/PlantUML 的联网语义在 5C 已细粒度证明，这里只回答一个问题：
**装配出的最终 HTML 是否满足 standalone policy，以及不满足时是否有合法证据。**

矩阵覆盖四类最终文档（普通 / KaTeX / Mermaid / remote+PlantUML 的成功与失败），
外加作者 raw HTML 的第四态、生产 v1 产物基线，以及两个「门禁不能是空转」的反证。
"""

import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from loopback_http import LoopbackServer, running_loopback  # noqa: E402
from standalone_closure import (  # noqa: E402
    assemble,
    assemble_and_scan,
    labels,
    payload_bytes,
    read_demo_html,
)

from tools import assemble_document as smoke_tool  # noqa: E402
from tools.standalone_closure import scan  # noqa: E402

KATEX_DOCUMENT = "行内公式 $a^2+b^2=c^2$ 与展示公式：\n\n$$\\int_0^1 x\\,dx$$\n"
MERMAID_DOCUMENT = "```mermaid\ngraph TD\n  A[开始] --> B[结束]\n```\n"
PLANTUML_DOCUMENT = "@startuml\nA -> B\n@enduml\n"
AUTHOR_REF = "https://raw.example.invalid/author.png"
RAW_HTML_DOCUMENT = '<img src="' + AUTHOR_REF + '">\n'
INJECTED_REF = "https://injected.example.invalid/a.png"


@pytest.fixture()
def loopback() -> Iterator[LoopbackServer]:
    """每个用例一个全新的 127.0.0.1 临时端口服务器。"""
    with running_loopback() as server:
        yield server


def _image_context(tmp_path: Path) -> dict:
    """Context that gives local images a base directory."""
    document = tmp_path / "doc.md"
    document.write_text("fixture", encoding="utf-8")
    return {"source_path": str(document), "output_path": str(tmp_path / "doc.html")}


# --- 载荷纪律 ---------------------------------------------------------------


def test_plain_markdown_is_standalone_and_carries_no_payload():
    result = assemble_and_scan("# 标题\n\n普通文本。\n")

    report = result["report"]
    html = result["assembled"]["html"]
    assert report["verdict"] == "standalone"
    assert labels(report) == ["viewer-css", "theme", "print", "viewer-js"]
    assert report["payload"]["resource_payload_bytes"] == 0
    assert "mermaid" not in html
    assert "KaTeX_" not in html


def test_a_formula_document_is_standalone_with_the_katex_style_only():
    result = assemble_and_scan(KATEX_DOCUMENT)

    report = result["report"]
    assert report["verdict"] == "standalone"
    assert payload_bytes(report, "style:katex") > 0
    assert payload_bytes(report, "script:mermaid") == 0
    assert payload_bytes(report, "boot:mermaid") == 0
    assert "data:font/woff2" in result["assembled"]["html"]


def test_a_mermaid_document_is_standalone_with_the_runtime_only():
    result = assemble_and_scan(MERMAID_DOCUMENT)

    report = result["report"]
    html = result["assembled"]["html"]
    assert report["verdict"] == "standalone"
    assert payload_bytes(report, "script:mermaid") > 0
    assert payload_bytes(report, "boot:mermaid") > 0
    assert payload_bytes(report, "style:katex") == 0
    assert 'class="mermaid"' in html
    assert "data:font/woff2" not in html

# --- 注入顺序与装配契约 -----------------------------------------------------


def test_injection_order_is_deterministic_across_the_channels():
    result = assemble_and_scan(KATEX_DOCUMENT + "\n" + MERMAID_DOCUMENT)

    report = result["report"]
    html = result["assembled"]["html"]
    assert labels(report) == [
        "viewer-css",
        "theme",
        "style:katex",
        "print",
        "viewer-js",
        "script:mermaid",
        "boot:mermaid",
    ]
    assert html.index('<style media="print">') < html.index("</head>")
    assert html.index("data:font/woff2") < html.index('<style media="print">')
    assert html.index("function applyTheme") < html.index('globalThis["mermaid"]')
    assert html.rindex("mermaid.run") < html.rindex("</body>")


def test_numbering_adds_exactly_one_injection_when_enabled():
    enabled = assemble_and_scan("# 一\n\n## 二\n", numbering=True)
    disabled = assemble_and_scan("# 一\n\n## 二\n")

    assert labels(enabled["report"]) == ["viewer-css", "theme", "print", "viewer-js", "numbering"]
    assert "numbering" not in labels(disabled["report"])


def test_an_unusable_template_is_refused():
    envelope = assemble_and_scan("# 标题\n")["envelope"]

    with pytest.raises(ValueError):
        assemble(envelope, template_name="does-not-exist")


# --- 本地资源（5A 的降级路径） ----------------------------------------------


def test_a_missing_local_image_is_degraded_with_a_warning(tmp_path):
    result = assemble_and_scan("![图](missing.png)\n", context=_image_context(tmp_path))

    report = result["report"]
    assert report["verdict"] == "degraded"
    assert [entry["ref"] for entry in report["degraded_resources"]] == ["missing.png"]
    assert report["degraded_resources"][0]["evidence"]["warning"]
    assert report["unexplained_external_resources"] == []


def test_a_local_image_without_a_base_directory_is_kept_without_a_warning():
    """5C 语义：local 无基准 → kept，且刻意不产生 warning。"""
    result = assemble_and_scan("![图](missing.png)\n")

    report = result["report"]
    assert result["envelope"]["warnings"] == []
    assert report["verdict"] == "degraded"
    assert report["degraded_resources"][0]["evidence"]["status"] == "kept"

# --- remote 与 PlantUML（5C 的联网与降级路径） ------------------------------


def test_a_remote_image_success_is_standalone(loopback):
    url = loopback.png("a.png")

    result = assemble_and_scan("![图](" + url + ")\n", allow_network=True)

    assert result["report"]["verdict"] == "standalone"
    assert 'src="data:image/png' in result["assembled"]["html"]
    assert loopback.stats.count("/png/a.png") == 1


def test_a_remote_image_failure_is_degraded_and_keeps_the_author_url(loopback):
    url = loopback.url("/status/404")

    result = assemble_and_scan("![图](" + url + ")\n", allow_network=True)

    report = result["report"]
    assert report["verdict"] == "degraded"
    assert [entry["ref"] for entry in report["degraded_resources"]] == [url]
    assert report["unexplained_external_resources"] == []
    assert url in result["assembled"]["html"], "失败必须保留作者原引用"


def test_a_plantuml_success_is_standalone(loopback):
    result = assemble_and_scan(
        PLANTUML_DOCUMENT,
        {"plantuml_server": loopback.url("/svg")},
        allow_network=True,
    )

    assert result["envelope"]["features"]["plantuml"] is True
    assert result["report"]["verdict"] == "standalone"
    assert "data:image/svg+xml" in result["assembled"]["html"]


def test_a_plantuml_failure_is_degraded_and_keeps_the_feature(loopback):
    server = loopback.url("/missing")

    result = assemble_and_scan(
        PLANTUML_DOCUMENT,
        {"plantuml_server": server},
        allow_network=True,
    )

    report = result["report"]
    assert result["envelope"]["features"]["plantuml"] is True, "资源失败不得改变语义 feature"
    assert report["verdict"] == "degraded"
    reference = report["degraded_resources"][0]["ref"]
    assert reference.startswith(server + "/svg/"), "必须保留原 PlantUML URL"
    assert report["unexplained_external_resources"] == []

# --- 作者 raw HTML（第四态） -------------------------------------------------


def test_a_raw_html_remote_image_is_an_author_reference():
    result = assemble_and_scan(RAW_HTML_DOCUMENT, author_owned_refs=[AUTHOR_REF])

    report = result["report"]
    assert report["verdict"] == "author_references"
    assert [entry["ref"] for entry in report["author_references"]] == [AUTHOR_REF]
    assert report["degraded_resources"] == []
    assert report["unexplained_external_resources"] == []
    assert report["problems"] == [], "作者自己写的引用不是转换失败"
    assert result["envelope"]["resources"]["items"] == [], "raw HTML 不进资源层（K13）"


def test_an_author_reference_never_hides_a_real_degradation(loopback):
    url = loopback.url("/status/404")
    markdown = RAW_HTML_DOCUMENT + "\n![图](" + url + ")\n"

    result = assemble_and_scan(markdown, allow_network=True, author_owned_refs=[AUTHOR_REF])

    report = result["report"]
    assert report["verdict"] == "degraded", "severity：degraded 必须压过 author_references"
    assert [entry["ref"] for entry in report["author_references"]] == [AUTHOR_REF]
    assert [entry["ref"] for entry in report["degraded_resources"]] == [url]
    assert report["unexplained_external_resources"] == []


# --- 生产基线 ---------------------------------------------------------------


def test_the_committed_production_demo_is_standalone():
    """生产 v1 产物是可测量的基线：strict 扫描（无 envelope）必须 standalone。

    demo 里有 3 个 `<a href="http…">` 导航链接：如果 checker 粗暴搜 "http"，这里必然失败。
    """
    html = read_demo_html()
    report = scan(html)

    assert report["verdict"] == "standalone"
    assert report["unexplained_external_resources"] == []
    assert report["payload"]["total_bytes"] == len(html.encode("utf-8"))


# --- smoke 页面生成器（tools/assemble_document.py） --------------------------


def test_the_smoke_page_builder_handles_a_relative_output_path(tmp_path, monkeypatch):
    """回归锁：相对 out 路径必须按调用者 cwd 解析。

    renderer 子进程的 cwd 是 `renderer/`，所以一个相对的 `source_path` 会被解析到
    错误目录，本地图片于是**静默**不内嵌（这条流程第一次跑出来时就是这个 bug）。
    """
    monkeypatch.chdir(tmp_path)

    built = smoke_tool.build(Path("smoke.html"))

    page = tmp_path / "smoke.html"
    assert built["report"]["verdict"] == "standalone"
    assert page.is_file()
    assert (tmp_path / "smoke-sources" / "local.png").is_file()
    assert "data:image/png" in page.read_text(encoding="utf-8")



# --- 反证：门禁不能是空转 ---------------------------------------------------


def test_an_injected_external_reference_is_a_failure():
    """反证 A：装配后凭空出现的引用（不在 envelope、不在 manifest）必须判 failure。"""
    result = assemble_and_scan("# 标题\n")
    html = result["assembled"]["html"].replace(
        "</body>", '<img src="' + INJECTED_REF + '">\n</body>', 1
    )

    report = scan(
        html,
        envelope=result["envelope"],
        injections=result["assembled"]["injections"],
    )

    assert report["verdict"] == "failure"
    assert [entry["ref"] for entry in report["unexplained_external_resources"]] == [INJECTED_REF]


def test_an_inlined_item_that_stayed_external_is_a_failure(loopback):
    """反证 B：manifest 说 inlined，最终 HTML 里却还是原 URL（模拟漏内嵌的 regression）。"""
    url = loopback.png("a.png")
    result = assemble_and_scan("![图](" + url + ")\n", allow_network=True)
    assembled = result["assembled"]["html"]
    assert "data:image/png" in assembled

    broken = re.sub(
        r'src="data:image/png;base64,[^"]*"',
        'src="' + url + '"',
        assembled,
        count=1,
    )

    report = scan(
        broken,
        envelope=result["envelope"],
        injections=result["assembled"]["injections"],
    )

    assert report["verdict"] == "failure"
    assert report["degraded_resources"] == [], "manifest 说谎时不得给出降级豁免"
