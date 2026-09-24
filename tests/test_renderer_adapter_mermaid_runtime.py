"""新 adapter 的 Mermaid runtime 通道（Phase 5B）。

AGENTS §9：只有文档真的含 Mermaid 时才交付 runtime；普通 Markdown 的 envelope 与 HTML
都不背这几 MB。
runtime 是 vendored 的**正式 browser 构建**（renderer/vendor/mermaid/<version>/，与 npm 包内
dist/mermaid.min.js 逐字节相同），build 与运行期各校验一次 SHA-256。本套件完全不联网：真正的
离线渲染由 opt-in 的 tests/browser 套件证明（见 docs/DEVELOPMENT.md）。
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from renderer_adapter import RENDERER_DIR, render, require_artifact, require_node  # noqa: E402

MERMAID_DOCUMENT = "```mermaid\ngraph LR\nA --> B\n```\n"
PLAIN_DOCUMENT = "只有普通文本。\n"
VENDOR_ROOT = RENDERER_DIR / "vendor" / "mermaid"
DIST_ROOT = RENDERER_DIR / "dist"
DIST_MERMAID = DIST_ROOT / "mermaid"
RUNTIME_ID = "mermaid"
SCRIPT_KEYS = {"id", "version", "script", "boot"}
UPSTREAM_PACKAGE = ROOT / "upstream" / "vscode-office" / "package.json"
DEPENDENCY_SECTIONS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)


def vendor_directory() -> Path:
    if not VENDOR_ROOT.is_dir():
        pytest.fail("缺少 renderer/vendor/mermaid：vendored runtime 必须入库。")
    versions = [
        path for path in sorted(VENDOR_ROOT.iterdir()) if (path / "metadata.json").is_file()
    ]
    assert len(versions) == 1, [path.name for path in versions]
    return versions[0]


def vendor_metadata() -> dict:
    return json.loads((vendor_directory() / "metadata.json").read_text(encoding="utf-8"))


def declared_upstream_mermaid_range() -> str:
    upstream = json.loads(UPSTREAM_PACKAGE.read_text(encoding="utf-8"))
    for section in DEPENDENCY_SECTIONS:
        declared = upstream.get(section, {}).get("mermaid")
        if declared:
            return declared
    raise AssertionError("pinned 上游没有声明 mermaid 依赖")


def scripts(envelope: dict) -> list:
    return envelope["resources"]["scripts"]


def runtime_items(envelope: dict) -> list:
    return [item for item in envelope["resources"]["items"] if item["kind"] == "runtime"]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- 选择性交付（AGENTS §9） -------------------------------------------------


def test_runtime_channel_is_present_and_empty_without_mermaid():
    envelope = render(PLAIN_DOCUMENT)
    payload = json.dumps(envelope, ensure_ascii=False)

    assert scripts(envelope) == []
    assert runtime_items(envelope) == []
    assert "mermaid.min.js" not in payload
    assert "mermaid.run" not in payload
    assert len(payload) < 200_000, "普通 Markdown 不得背上 runtime"


def test_a_mermaid_document_delivers_the_vendored_runtime():
    envelope = render(MERMAID_DOCUMENT)
    (script,) = scripts(envelope)

    assert set(script) == SCRIPT_KEYS, script.keys()
    assert script["id"] == RUNTIME_ID
    assert script["version"] == vendor_directory().name
    assert script["script"] == (vendor_directory() / "mermaid.min.js").read_text(encoding="utf-8")
    assert "mermaid.run" in script["boot"] and "div.mermaid" in script["boot"]


def test_the_delivered_runtime_is_the_vendored_artifact_byte_for_byte():
    """最强的一条：交付的字节必须等于 vendored 产物，不存在 CDN / 替换来源的空间。"""
    (script,) = scripts(render(MERMAID_DOCUMENT))
    metadata = vendor_metadata()

    assert len(script["script"].encode("utf-8")) == metadata["artifact_bytes"]
    digest = hashlib.sha256(script["script"].encode("utf-8")).hexdigest()
    assert digest == metadata["artifact_sha256"]


def test_delivery_is_recorded_in_the_manifest():
    (item,) = runtime_items(render(MERMAID_DOCUMENT))

    assert item["source"] == "vendored" and item["status"] == "inlined"
    assert item["ref"] == RUNTIME_ID + "@" + vendor_directory().name
    assert item["mime"] == "text/javascript"
    assert Path(item["resolved"]).is_file()
    assert Path(item["resolved"]).parent == DIST_MERMAID


def test_delivery_is_not_a_warning():
    assert render(MERMAID_DOCUMENT)["warnings"] == []


def test_the_adapter_delivers_the_runtime_instead_of_injecting_it():
    """adapter 不自己拼页面：html 里没有 script。

    与 resources.styles 同一约定：资源通道负责交付，页面装配属 assembler。
    """
    envelope = render(MERMAID_DOCUMENT)
    (script,) = scripts(envelope)

    assert "<script" not in envelope["html"]
    assert "mermaid.min.js" not in envelope["html"]
    assert "mermaid.initialize" not in envelope["html"]
    assert "<script" not in script["boot"]
    assert "http" not in script["boot"], "boot 不得引用外部资源"


def test_the_runtime_channel_and_the_feature_flag_agree():
    """两份判断（fence predicate / render 阶段写的 meta 标记）必须同进同退。"""
    documents = [
        MERMAID_DOCUMENT,
        "```\ngantt\ntitle x\n```\n",
        "```js\ngantt\ntitle x\n```\n",
        "```mermaid  \ngraph LR\nA --> B\n```\n",
        "```\nsequenceDiagram\nA->>B: hi\n```\n",
        "```python\nprint(1)\n```\n",
        "```mermaid\n\n```\n",
        PLAIN_DOCUMENT,
        '<div class="mermaid">graph TD</div>\n',
        "@startuml\nA -> B\n@enduml\n",
    ]
    for document in documents:
        envelope = render(document)
        assert envelope["features"]["mermaid"] is bool(scripts(envelope)), document


def test_raw_html_mermaid_container_does_not_pull_the_runtime():
    """raw HTML 不是 Markdown 语义：原样保留，也不触发 runtime（与 feature 判断一致）。"""
    envelope = render('<div class="mermaid">graph TD</div>\n')

    assert envelope["features"]["mermaid"] is False
    assert scripts(envelope) == []
    assert '<div class="mermaid">graph TD</div>' in envelope["html"]


def test_plantuml_document_does_not_pull_the_mermaid_runtime():
    envelope = render("@startuml\nA -> B\n@enduml\n")

    assert envelope["features"]["plantuml"] is True
    assert scripts(envelope) == []


def test_delivery_is_deterministic_across_conversions():
    first = scripts(render(MERMAID_DOCUMENT))[0]
    second = scripts(render(MERMAID_DOCUMENT))[0]

    assert first == second


# --- vendored 来源与 build 产物 --------------------------------------------


def test_vendored_artifact_matches_its_metadata():
    artifact = vendor_directory() / "mermaid.min.js"
    metadata = vendor_metadata()

    assert artifact.stat().st_size == metadata["artifact_bytes"]
    assert sha256_of(artifact) == metadata["artifact_sha256"]
    assert metadata["artifact"] == "dist/mermaid.min.js"


def test_vendored_metadata_is_traceable_and_inside_the_upstream_range():
    metadata = vendor_metadata()
    version = vendor_directory().name

    assert metadata["version"] == version
    assert metadata["source"] == "npm"
    assert metadata["package"] == "mermaid@" + version
    assert metadata["tarball"].endswith("/mermaid-" + version + ".tgz")
    assert len(str(metadata["tarball_sha1"])) == 40
    assert len(str(metadata["artifact_sha256"])) == 64
    assert metadata["license"] == "MIT"
    license_text = (vendor_directory() / "LICENSE").read_text(encoding="utf-8")
    assert license_text.startswith("The MIT License")
    assert declared_upstream_mermaid_range() == "^" + version, (
        "vendored 版本必须落在 pinned 上游声明的 mermaid 区间内"
    )


def test_the_runtime_bundle_is_self_contained():
    """离线可用性的前提：正式 browser 构建自包含。

    具体是：无动态 import、无 sourcemap 引用、导出全局 mermaid。
    """
    (script,) = scripts(render(MERMAID_DOCUMENT))
    source = script["script"]

    assert "import(" not in source
    assert "sourceMappingURL" not in source
    assert 'globalThis["mermaid"]' in source


def test_the_renderer_does_not_depend_on_the_mermaid_package():
    manifest = json.loads((RENDERER_DIR / "package.json").read_text(encoding="utf-8"))

    assert "mermaid" not in manifest.get("dependencies", {})
    assert "mermaid" not in manifest.get("devDependencies", {}), (
        "runtime 是 vendored 资产，不是构建依赖"
    )


def test_the_build_publishes_the_runtime_next_to_the_bundle():
    require_artifact()

    for name in ("mermaid.min.js", "metadata.json", "LICENSE"):
        assert (DIST_MERMAID / name).is_file(), name
    assert (DIST_MERMAID / "mermaid.min.js").read_bytes() == (
        vendor_directory() / "mermaid.min.js"
    ).read_bytes(), "dist 里的 runtime 必须与 vendored 产物逐字节相同"
    published = json.loads((DIST_MERMAID / "metadata.json").read_text(encoding="utf-8"))
    assert published == vendor_metadata()
    assert not (DIST_ROOT / ".staging").exists(), "构建结束后不得留下 staging 目录"


def test_the_build_publishes_the_katex_assets_unaffected_by_mermaid():
    """5A 的资产不能因为 5B 的替换流程而丢失或错位。"""
    require_artifact()
    katex = DIST_ROOT / "katex"

    assert (katex / "katex.min.css").is_file()
    assert (katex / "fonts" / "KaTeX_Main-Regular.woff2").is_file()
    assert sum(1 for _ in katex.rglob("*") if _.is_file()) == 61


def test_the_artifact_runs_without_the_renderer_node_modules(tmp_path: Path):
    """dist 单独拷出去（旁边没有 node_modules）也能交付 runtime。"""
    artifact = require_artifact()
    node = require_node()
    isolated = tmp_path / "dist"
    isolated.mkdir()
    shutil.copy2(artifact, isolated / "renderer.cjs")
    shutil.copytree(DIST_ROOT / "katex", isolated / "katex")
    shutil.copytree(DIST_MERMAID, isolated / "mermaid")
    assert not (tmp_path / "node_modules").exists()

    completed = subprocess.run(
        [node, str(isolated / "renderer.cjs")],
        input=json.dumps({"markdown": MERMAID_DOCUMENT, "options": {}, "context": {}}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp_path),
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    envelope = json.loads(completed.stdout)
    (script,) = scripts(envelope)
    assert script["version"] == vendor_directory().name
    assert envelope["warnings"] == []


def test_a_missing_runtime_degrades_instead_of_failing(tmp_path: Path):
    """runtime 缺失不得让转换失败（AGENTS §8）：warning + 不交付，其余照常。"""
    artifact = require_artifact()
    node = require_node()
    isolated = tmp_path / "dist"
    isolated.mkdir()
    shutil.copy2(artifact, isolated / "renderer.cjs")
    shutil.copytree(DIST_ROOT / "katex", isolated / "katex")

    completed = subprocess.run(
        [node, str(isolated / "renderer.cjs")],
        input=json.dumps({"markdown": MERMAID_DOCUMENT, "options": {}, "context": {}}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp_path),
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    envelope = json.loads(completed.stdout)
    assert scripts(envelope) == []
    assert any("Mermaid runtime 不可用" in warning for warning in envelope["warnings"])
    assert '<div class="mermaid">' in envelope["html"], "容器仍在：缺 runtime 不影响语义层"

