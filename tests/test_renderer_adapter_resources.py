"""新 adapter 的资源层契约（Phase 5A）：protocol v2 的 resources 通道。

范围：
  * envelope 形状：resources 必在（items / styles），没有资源时也是空结构；
  * Markdown 本地图片 → data URI，并逐条记入 manifest；失败保留原引用 + 可读 warning；
  * data: / http(s): / 协议相对 / 其它 scheme 一律不碰（远程抓取属 5C）；
  * **raw HTML 里的资源引用不参与内嵌**：K13 的边界不得扩大；
  * KaTeX 载荷纪律（K21）与自包含 build artifact（运行期不依赖 renderer/node_modules）。

warnings 保持用户可读字符串数组：成功内嵌不进 warnings，状态记在 manifest（T7 已登记改写）。
"""

import base64
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from renderer_adapter import (  # noqa: E402
    RENDERER_DIR,
    render,
    require_artifact,
    require_node,
)

# 与 tests/test_image_embedding.py 一致的 1x1 PNG，便于两侧语义逐条对照。
MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)
PNG_PREFIX = "data:image/png;base64,"
MISSING_WARNING = "图片无法内嵌，保留原引用："
KATEX_STYLE_ID = "katex"
FONT_FAMILY_MARKER = "KaTeX_AMS"
FONT_DATA_URI = "url(data:font/woff2;base64,"
IMAGE_KIND = "image"
CSS_RESOURCE_KIND = "css-resource"
STATUSES = {"inlined", "kept", "failed"}
BASE_ITEM_KEYS = {"kind", "source", "ref", "status"}
OPTIONAL_ITEM_KEYS = {"mime", "resolved"}

# K21 的两个负例：代码块里的 $ 与散文里的价格都不是公式。
KATEX_CODE_AND_PRICE = (
    '```python\nprint("Budget: $100; remaining: $200")\n```\n\n价格 $100 美元，转义 \\$5。'
)


def context_for(tmp_path: Path, source_name: str = "doc.md") -> dict:
    return {
        "source_path": str(tmp_path / source_name),
        "output_path": str(tmp_path / "out" / "doc.html"),
        "document_map": {},
    }


def render_doc(markdown: str, tmp_path: Path) -> dict:
    return render(markdown, context=context_for(tmp_path))


def write_png(directory: Path, name: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(MINIMAL_PNG)
    return path


def img_sources(html: str) -> list[str]:
    """所有 src 属性值（含作者写的 raw HTML），顺序即文档顺序。"""
    return re.findall(r'\bsrc="([^"]*)"', html)


def img_source(html: str) -> str:
    sources = img_sources(html)
    assert sources, html
    return sources[0]


def is_embedded(src: str) -> bool:
    if not src.startswith(PNG_PREFIX):
        return False
    return base64.b64decode(src.split(",", 1)[1], validate=False) == MINIMAL_PNG


def manifest(envelope: dict, kind: str) -> list[dict]:
    return [item for item in envelope["resources"]["items"] if item["kind"] == kind]


def assert_manifest_shape(envelope: dict) -> None:
    resources = envelope["resources"]
    assert set(resources) == {"items", "styles", "scripts"}, resources
    assert isinstance(resources["items"], list) and isinstance(resources["styles"], list)
    assert isinstance(resources["scripts"], list)
    for item in resources["items"]:
        keys = set(item)
        assert BASE_ITEM_KEYS <= keys, item
        assert keys <= BASE_ITEM_KEYS | OPTIONAL_ITEM_KEYS, item
        assert item["status"] in STATUSES, item
        assert isinstance(item["ref"], str) and isinstance(item["source"], str), item
    for style in resources["styles"]:
        assert set(style) == {"id", "css"}, style
        assert isinstance(style["id"], str) and isinstance(style["css"], str)
    # scripts 是 5B 的 additive 通道：形状同样是契约（细节见 mermaid runtime 套件）。
    for script in resources["scripts"]:
        assert set(script) == {"id", "version", "script", "boot"}, script
        assert all(isinstance(value, str) for value in script.values()), script


# --- envelope 形状 ---------------------------------------------------------


def test_resources_channel_is_always_present_even_when_empty():
    envelope = render("只有普通文本。\n")

    assert set(envelope["resources"]) == {"items", "styles", "scripts"}
    assert envelope["resources"] == {"items": [], "styles": [], "scripts": []}
    assert "assets" not in envelope, "v1 的 assets.css 不属于 v2"
    assert envelope["warnings"] == []


def test_manifest_shape_is_the_v2_contract(tmp_path: Path):
    write_png(tmp_path, "pic.png")

    envelope = render_doc("![本地](pic.png)\n\n![远程](https://example.com/a.png)\n", tmp_path)

    assert_manifest_shape(envelope)
    assert [item["status"] for item in manifest(envelope, IMAGE_KIND)] == ["inlined", "kept"]


def test_successful_embedding_reports_no_warning(tmp_path: Path):
    """成功不是错误：状态进 manifest，warnings 只留真实需要作者注意的情况（K15 不改写）。"""
    write_png(tmp_path, "pic.png")

    envelope = render_doc("![a](pic.png)\n", tmp_path)

    assert envelope["warnings"] == []
    assert manifest(envelope, IMAGE_KIND)[0]["status"] == "inlined"


# --- Markdown 本地图片 -----------------------------------------------------


def test_relative_local_image_becomes_a_data_uri(tmp_path: Path):
    image = write_png(tmp_path, "pic.png")

    envelope = render_doc("![a](pic.png)\n", tmp_path)

    assert is_embedded(img_source(envelope["html"]))
    (item,) = manifest(envelope, IMAGE_KIND)
    assert set(item) == {"kind", "source", "ref", "status", "mime", "resolved"}, item
    assert item["kind"] == IMAGE_KIND and item["source"] == "local" and item["status"] == "inlined"
    assert item["ref"] == "pic.png" and item["mime"] == "image/png"
    assert Path(item["resolved"]) == image


def test_absolute_local_image_becomes_a_data_uri(tmp_path: Path):
    image = write_png(tmp_path, "pic.png")

    envelope = render_doc("![a](" + image.as_posix() + ")\n", tmp_path)

    assert is_embedded(img_source(envelope["html"]))


def test_image_path_with_spaces_and_unicode_is_embedded(tmp_path: Path):
    write_png(tmp_path, "图片 one.png")

    envelope = render_doc("![a](<图片 one.png>)\n", tmp_path)

    assert is_embedded(img_source(envelope["html"]))


def test_repeated_references_are_all_embedded(tmp_path: Path):
    write_png(tmp_path, "pic.png")

    envelope = render_doc("![a](pic.png) 与 ![b](pic.png)\n", tmp_path)

    sources = img_sources(envelope["html"])
    assert len(sources) == 2
    assert all(is_embedded(src) for src in sources)


def test_image_inside_a_link_is_embedded_but_the_link_is_kept(tmp_path: Path):
    write_png(tmp_path, "pic.png")

    envelope = render_doc("[![a](pic.png)](https://example.com)\n", tmp_path)

    assert 'href="https://example.com"' in envelope["html"]
    assert is_embedded(img_source(envelope["html"]))


def test_heading_image_is_embedded_in_the_body_but_the_toc_keeps_alt_text(tmp_path: Path):
    """K14：正文标题可以带内嵌图片，TOC 侧仍只保留可见文本。"""
    write_png(tmp_path, "pic.png")

    envelope = render_doc("# ![alt](pic.png)\n", tmp_path)
    (heading,) = envelope["headings"]

    assert is_embedded(img_source(heading["inline_html"]))
    assert heading["toc_inline_html"] == "alt"
    assert "data:" not in heading["toc_inline_html"]


def test_source_image_file_is_not_modified(tmp_path: Path):
    image = write_png(tmp_path, "pic.png")
    before = image.read_bytes()

    render_doc("![a](pic.png)\n", tmp_path)

    assert image.read_bytes() == before
# --- 失败与非本地引用 ------------------------------------------------------


def test_missing_local_image_keeps_src_and_warns(tmp_path: Path):
    envelope = render_doc("![a](missing.png)\n", tmp_path)

    assert img_source(envelope["html"]) == "missing.png"
    assert len(envelope["warnings"]) == 1
    assert envelope["warnings"][0].startswith(MISSING_WARNING)
    assert "missing.png" in envelope["warnings"][0]
    assert manifest(envelope, IMAGE_KIND) == [
        {"kind": IMAGE_KIND, "source": "local", "ref": "missing.png", "status": "failed"}
    ]


def test_a_missing_unicode_image_keeps_the_encoded_src_but_reads_in_the_warning(tmp_path: Path):
    """src 是给浏览器的 URL，warning 是给作者的路径。"""
    envelope = render_doc("![a](图片/示例.png)\n", tmp_path)

    assert img_source(envelope["html"]) == "%E5%9B%BE%E7%89%87/%E7%A4%BA%E4%BE%8B.png"
    assert any("图片/示例.png" in warning for warning in envelope["warnings"])
    assert all("%E5" not in warning for warning in envelope["warnings"])


def test_existing_data_uri_is_left_untouched(tmp_path: Path):
    uri = PNG_PREFIX + base64.b64encode(MINIMAL_PNG).decode("ascii")

    envelope = render_doc("![a](" + uri + ")\n", tmp_path)

    assert is_embedded(img_source(envelope["html"]))
    assert envelope["warnings"] == []
    (item,) = manifest(envelope, IMAGE_KIND)
    assert item["source"] == "data" and item["status"] == "kept"


def test_remote_image_is_kept_when_fetching_is_disabled(tmp_path: Path):
    """T1 由 Phase 5C 改写：remote 的**行为**现在取决于 `fetch_remote_resources`。

    这里的 harness 默认注入 `fetch_remote_resources = false`（保证完整测试不访问公网），
    因此 remote 只记 kept、不改 HTML、也不报 warning；**联网成功/失败的真实语义**由
    tests/test_renderer_network.py 用 127.0.0.1 loopback 服务器证明。
    """
    sources = [
        "http://example.com/a.png",
        "https://example.com/a.png",
        "//cdn.example.com/a.png",
    ]
    for source in sources:
        envelope = render_doc("![a](" + source + ")\n", tmp_path)

        assert img_source(envelope["html"]) == source
        assert envelope["warnings"] == []
        (item,) = manifest(envelope, IMAGE_KIND)
        assert item["source"] == "remote" and item["status"] == "kept", item


def test_file_scheme_image_keeps_the_markdown_it_default(tmp_path: Path):
    """其它 scheme 不属本地资源：file: 仍由 markdown-it 处理（K13）。"""
    envelope = render_doc("![x](file:///C:/a.png)\n", tmp_path)

    assert "<img" not in envelope["html"]
    assert envelope["warnings"] == []


def test_image_without_source_context_is_kept_without_a_warning():
    """5C 的 classify-first：缺 source_path 只影响 local 解析，不再让 manifest 为空。

    local 没有基准 → kept（不是 failed：缺上下文不等于文件错误），data: / remote 也照常记录。
    """
    envelope = render("![a](pic.png)\n")

    assert img_source(envelope["html"]) == "pic.png"
    assert envelope["resources"]["items"] == [
        {"kind": "image", "source": "local", "ref": "pic.png", "status": "kept"}
    ]
    assert envelope["resources"]["styles"] == []
    assert envelope["resources"]["scripts"] == []
    assert envelope["warnings"] == []


# --- raw HTML 边界（K13：不得扩大） ----------------------------------------


def test_raw_html_image_is_not_embedded(tmp_path: Path):
    """collector 只看 Markdown image token：作者写在 raw HTML 里的引用保持原样。"""
    write_png(tmp_path, "pic.png")

    envelope = render_doc("<img src=\"./pic.png\" alt=\"raw\">\n", tmp_path)

    assert '<img src="./pic.png"' in envelope["html"]
    assert "data:" not in envelope["html"]
    assert manifest(envelope, IMAGE_KIND) == []


def test_raw_html_style_url_is_not_resolved(tmp_path: Path):
    write_png(tmp_path, "pic.png")

    envelope = render_doc("<div style=\"background-image:url('./pic.png')\">raw</div>\n", tmp_path)

    assert "url('./pic.png')" in envelope["html"]
    assert envelope["resources"] == {"items": [], "styles": [], "scripts": []}


def test_raw_html_and_markdown_images_of_the_same_file_differ(tmp_path: Path):
    write_png(tmp_path, "pic.png")

    envelope = render_doc("raw: <img src=\"./pic.png\">\n\nmarkdown: ![a](pic.png)\n", tmp_path)
    html = envelope["html"]

    assert '<img src="./pic.png"' in html, "raw HTML 原样保留"
    assert is_embedded(img_sources(html)[-1]), "只有 Markdown image token 被内嵌"
    assert len(manifest(envelope, IMAGE_KIND)) == 1


# --- KaTeX：载荷纪律（K21）+ 自包含资产 -----------------------------------


def test_plain_prose_carries_no_katex_payload(tmp_path: Path):
    envelope = render_doc("只有普通文本，没有任何公式。\n", tmp_path)

    assert envelope["resources"]["styles"] == []
    assert "data:font" not in json.dumps(envelope, ensure_ascii=False)
    assert 'class="katex' not in envelope["html"]


def test_a_dollar_in_code_or_as_a_price_is_not_a_formula(tmp_path: Path):
    envelope = render_doc(KATEX_CODE_AND_PRICE, tmp_path)

    assert envelope["resources"]["styles"] == [], "散文里的 $ 不能把字体拖进来"
    assert 'class="katex' not in envelope["html"]


def test_a_formula_carries_the_self_contained_stylesheet(tmp_path: Path):
    envelope = render_doc("圆的面积 $A = \\pi r^2$ 适合嵌入解释。\n", tmp_path)

    assert 'class="katex' in envelope["html"]
    (style,) = envelope["resources"]["styles"]
    assert style["id"] == KATEX_STYLE_ID
    assert FONT_FAMILY_MARKER in style["css"]
    assert FONT_DATA_URI in style["css"]
    assert "url(fonts/" not in style["css"], "字体的本地引用必须全部内嵌"
    assert envelope["warnings"] == []


def test_malformed_formula_keeps_the_stylesheet(tmp_path: Path):
    """错误标记仍是 KaTeX 标记，同样需要样式表。"""
    envelope = render_doc("坏公式 $\\frac{1}{$ 后面正常。\n", tmp_path)

    assert "katex-error" in envelope["html"]
    assert FONT_FAMILY_MARKER in envelope["resources"]["styles"][0]["css"]


def test_katex_fonts_are_reported_as_css_resource_items(tmp_path: Path):
    envelope = render_doc("公式 $a^2$。\n", tmp_path)

    fonts = manifest(envelope, CSS_RESOURCE_KIND)
    assert fonts, "KaTeX 样式必须把字体交给资源层"
    assert len(fonts) == len({item["ref"] for item in fonts}), "同一字体不应重复计入"
    assert all(item["status"] == "inlined" for item in fonts)
    assert all(item["mime"].startswith("font/") for item in fonts)
    assert_manifest_shape(envelope)


# --- 自包含 build artifact -------------------------------------------------


def test_build_emits_a_katex_asset_directory_with_every_referenced_font():
    require_artifact()
    asset_directory = RENDERER_DIR / "dist" / "katex"
    css = (asset_directory / "katex.min.css").read_text(encoding="utf-8")

    references = re.findall(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", css)
    assert references, "KaTeX 样式必须引用字体"
    for reference in references:
        assert (asset_directory / reference).is_file(), reference
    assert FONT_FAMILY_MARKER in css


def test_the_artifact_runs_without_the_renderer_node_modules(tmp_path: Path):
    """dist/renderer.cjs + dist/katex/ 单独拷出去（旁边没有 node_modules）仍能内嵌字体。"""
    artifact = require_artifact()
    node = require_node()
    isolated = tmp_path / "dist"
    isolated.mkdir()
    shutil.copy2(artifact, isolated / "renderer.cjs")
    shutil.copytree(RENDERER_DIR / "dist" / "katex", isolated / "katex")
    assert not (tmp_path / "node_modules").exists()

    completed = subprocess.run(
        [node, str(isolated / "renderer.cjs")],
        input=json.dumps({"markdown": "公式 $a^2$。\n", "options": {}, "context": {}}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp_path),
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    envelope = json.loads(completed.stdout)
    (style,) = envelope["resources"]["styles"]
    assert FONT_DATA_URI in style["css"]
    assert envelope["warnings"] == []
