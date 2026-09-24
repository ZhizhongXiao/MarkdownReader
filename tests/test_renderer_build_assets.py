"""vendored runtime 的构建 gate（Phase 5B）。

与 Phase 3 的 upstream provenance gate 同一纪律：来源与产物必须可核对，篡改或缺件一律**拒绝构建**，
且失败不触碰 dist（不留「看起来可用、实际不同步」的 runtime set）。

fixture 复用 tests/test_renderer_build_provenance.py 的临时（嵌套）git 仓库：不联网、不改动当前
工作区、不对任何分支 force/reset；真实仓库的 renderer/dist 只读取哈希，本模块从不写入它。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from renderer_adapter import ARTIFACT, RENDERER_DIR  # noqa: E402
from test_renderer_build_provenance import (  # noqa: E402
    SENTINEL,
    _git,
    _run_build,
    _sha256,
)

VENDOR_VERSION = "11.15.0"
REUSED_SOURCES = (
    "src/service/markdown/ext/markdown-it-obsidian.js",
    "src/service/markdown/ext/markdown-it-katex.js",
)


def _vendor_layout(tmp_path: Path) -> Path:
    """provenance fixture 的变体：upstream 里**提交**了被复用的上游源文件。

    否则 build 会先停在「缺少 pinned 上游源文件」，走不到 vendored runtime 的 gate。
    仍不联网、不写真实仓库：dist 里只放 sentinel。
    """
    repo = tmp_path / "repo"
    sub = repo / "upstream" / "vscode-office"
    sub.mkdir(parents=True)
    _git(["init", "-q"], sub)
    _git(["config", "user.email", "renderer-test@example.invalid"], sub)
    _git(["config", "user.name", "MarkdownReader Renderer Test"], sub)
    for relative in REUSED_SOURCES:
        target = sub / Path(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("// pinned placeholder\n", encoding="utf-8")
    _git(["add", "-A"], sub)
    _git(["commit", "-q", "-m", "pinned state"], sub)
    pinned = _git(["rev-parse", "HEAD"], sub).stdout.strip()

    _git(["init", "-q"], repo)
    gitlink = "160000," + pinned + ",upstream/vscode-office"
    _git(["update-index", "--add", "--cacheinfo", gitlink], repo)
    (repo / "upstream" / "pin.json").write_text(
        json.dumps({"schema": 1, "pinned_commit": pinned}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    dist = repo / "renderer" / "dist"
    dist.mkdir(parents=True)
    (dist / "renderer.cjs").write_text(SENTINEL, encoding="utf-8")
    return repo


def _write_vendor(layout: Path, *, artifact: bytes, license_text: str, metadata: dict) -> None:
    vendor = layout / "renderer" / "vendor" / "mermaid" / VENDOR_VERSION
    vendor.mkdir(parents=True, exist_ok=True)
    (vendor / "mermaid.min.js").write_bytes(artifact)
    (vendor / "LICENSE").write_text(license_text, encoding="utf-8")
    (vendor / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _assert_refused_without_touching_dist(layout: Path, *, expect: str) -> None:
    real_before = _sha256(ARTIFACT)
    sentinel = layout / "renderer" / "dist" / "renderer.cjs"

    completed = _run_build(("--repo-root", str(layout)))

    assert completed.returncode != 0, completed.stdout
    assert "拒绝构建" in completed.stderr, completed.stderr
    assert expect in completed.stderr, completed.stderr
    assert sentinel.read_text(encoding="utf-8") == SENTINEL, "校验失败不得触碰 dist"
    assert not (layout / "renderer" / "dist" / ".staging").exists(), "校验失败不得留下 staging"
    assert _sha256(ARTIFACT) == real_before, "真实 renderer/dist 不得被改写"


def test_a_missing_vendor_directory_refuses_the_build(tmp_path: Path):
    layout = _vendor_layout(tmp_path)

    _assert_refused_without_touching_dist(layout, expect="renderer/vendor/mermaid")


def test_a_tampered_artifact_refuses_the_build(tmp_path: Path):
    """metadata 声称的是上游发布的 SHA-256，产物却不是它 → 必须拒绝。"""
    layout = _vendor_layout(tmp_path)
    published = json.loads(
        (RENDERER_DIR / "vendor" / "mermaid" / VENDOR_VERSION / "metadata.json").read_text(
            encoding="utf-8"
        )
    )
    _write_vendor(
        layout,
        artifact=b"// not the published artifact\n",
        license_text="MIT\n",
        metadata={
            "version": VENDOR_VERSION,
            "artifact": "dist/mermaid.min.js",
            "artifact_sha256": published["artifact_sha256"],
            "artifact_bytes": published["artifact_bytes"],
        },
    )

    _assert_refused_without_touching_dist(layout, expect="SHA-256")


def test_a_metadata_version_mismatch_refuses_the_build(tmp_path: Path):
    """产物字节完全正确，只是 metadata 的版本与目录名不符 → 仍拒绝（metadata 是审计记录）。"""
    layout = _vendor_layout(tmp_path)
    published_directory = RENDERER_DIR / "vendor" / "mermaid" / VENDOR_VERSION
    artifact = (published_directory / "mermaid.min.js").read_bytes()
    published = json.loads((published_directory / "metadata.json").read_text(encoding="utf-8"))
    metadata = dict(published)
    metadata["version"] = "9.9.9"
    _write_vendor(
        layout,
        artifact=artifact,
        license_text="MIT\n",
        metadata=metadata,
    )

    _assert_refused_without_touching_dist(layout, expect="与目录名")
