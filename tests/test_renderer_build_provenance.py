"""renderer build 的 upstream provenance gate（Phase 3 closeout）。

证明 `npm run build` 不会在「checkout 不等于 pinned gitlink」时仍然成功并谎报来源：

  * 正常 pinned 状态：--check-provenance 通过，pin manifest == gitlink == checkout；
  * 未 pin 的 checkout：build 失败、不写 dist、给可操作提示；
  * git 缺失：明确失败，不猜 commit。

fixture 是临时目录里的真实（嵌套）git 仓库：不联网、不改动当前工作区、不对任何分支做
force/reset。真实仓库的 renderer/dist 只读取哈希，本模块从不写入它。
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from renderer_adapter import ARTIFACT, RENDERER_DIR, require_node, run_adapter  # noqa: E402

BUILD_SCRIPT = RENDERER_DIR / "build" / "build.js"
PIN_MANIFEST = ROOT / "upstream" / "pin.json"
SENTINEL = "SENTINEL-DO-NOT-OVERWRITE\n"


def _git(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _require_git() -> None:
    if shutil.which("git") is None:
        pytest.skip("git 不在 PATH 上（平台工具缺失）：只跳过 provenance 检查。")


def _run_build(args: tuple = (), env: dict | None = None) -> subprocess.CompletedProcess:
    node = require_node()
    return subprocess.run(
        [node, str(BUILD_SCRIPT), *args],
        cwd=str(RENDERER_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


@pytest.fixture()
def mismatched_layout(tmp_path: Path) -> Path:
    """构造 checkout != authoritative gitlink 的真实 git 布局（离线）。"""
    _require_git()
    repo = tmp_path / "repo"
    sub = repo / "upstream" / "vscode-office"
    sub.mkdir(parents=True)

    _git(["init", "-q"], sub)
    _git(["config", "user.email", "renderer-test@example.invalid"], sub)
    _git(["config", "user.name", "MarkdownReader Renderer Test"], sub)
    (sub / "source.js").write_text("// pinned\n", encoding="utf-8")
    _git(["add", "-A"], sub)
    _git(["commit", "-q", "-m", "pinned state"], sub)
    pinned = _git(["rev-parse", "HEAD"], sub).stdout.strip()

    (sub / "source.js").write_text("// not pinned\n", encoding="utf-8")
    _git(["add", "-A"], sub)
    _git(["commit", "-q", "-m", "later state"], sub)
    checkout = _git(["rev-parse", "HEAD"], sub).stdout.strip()
    assert pinned and checkout and pinned != checkout

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


def test_check_provenance_passes_on_the_pinned_checkout():
    completed = _run_build(("--check-provenance",))

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["ok"] is True
    assert report["pinned_commit"] == report["gitlink_commit"] == report["checkout_commit"]
    manifest = json.loads(PIN_MANIFEST.read_text(encoding="utf-8"))
    assert report["pinned_commit"] == manifest["pinned_commit"]


def test_mismatched_checkout_fails_build_and_keeps_dist_untouched(mismatched_layout: Path):
    real_before = _sha256(ARTIFACT)
    sentinel = mismatched_layout / "renderer" / "dist" / "renderer.cjs"

    completed = _run_build(("--repo-root", str(mismatched_layout)))

    assert completed.returncode != 0, completed.stdout
    assert "拒绝构建" in completed.stderr
    assert "git submodule update --init --recursive" in completed.stderr
    assert sentinel.read_text(encoding="utf-8") == SENTINEL
    assert _sha256(ARTIFACT) == real_before, "真实 renderer/dist 不得被改写"


def test_mismatched_checkout_reports_both_commits(mismatched_layout: Path):
    manifest = json.loads((mismatched_layout / "upstream" / "pin.json").read_text(encoding="utf-8"))
    submodule = mismatched_layout / "upstream" / "vscode-office"
    checkout = _git(["rev-parse", "HEAD"], submodule).stdout.strip()

    completed = _run_build(("--repo-root", str(mismatched_layout), "--check-provenance"))

    assert completed.returncode != 0
    combined = completed.stdout + completed.stderr
    assert manifest["pinned_commit"] in combined
    assert checkout in combined
    assert checkout != manifest["pinned_commit"]


def test_git_missing_fails_with_a_clear_message(tmp_path: Path):
    node = require_node()
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = {"PATH": str(empty_bin)}
    for key in ("SystemRoot", "windir", "TEMP", "TMP", "PATHEXT", "COMSPEC"):
        if os.environ.get(key):
            env[key] = os.environ[key]

    completed = subprocess.run(
        [node, str(BUILD_SCRIPT), "--check-provenance"],
        cwd=str(RENDERER_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    assert completed.returncode != 0
    assert "git" in completed.stderr, completed.stderr
    assert "gitlink_commit  = (未知)" in completed.stderr, "git 缺失时不得猜测 commit"


def test_info_reports_provenance_fields():
    _require_git()
    completed = run_adapter("", args=("--info",))

    assert completed.returncode == 0, completed.stderr
    info = json.loads(completed.stdout)
    assert info["ok"] is True
    assert info["provenance_ok"] is True
    assert info["provenance_problems"] == []
    assert info["pinned_commit"] == info["gitlink_commit"] == info["checkout_commit"]
    entry = _git(["ls-files", "-s", "upstream/vscode-office"], ROOT)
    assert entry.stdout.split()[1] == info["gitlink_commit"]
