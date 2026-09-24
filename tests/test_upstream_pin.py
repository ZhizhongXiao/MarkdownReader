"""上游 vscode-office pin 契约（Phase 2）。

事实源分工（三者不许各说各话）：

  * .gitmodules 是 upstream 仓库位置的来源；
  * superproject 的 submodule gitlink 是 pinned commit 的权威来源；
  * upstream/pin.json 是 metadata / 集成证据 manifest，不是第二套版本系统。

策略：.gitmodules、gitlink 与 pin.json 属于必需的仓库状态，缺失即失败，并给出可执行提示
`git submodule update --init --recursive`；不允许因为 submodule 未初始化而 skip，
那会让完整测试假绿。只有真正缺少平台工具（git / pwsh）时才 skip，
且只跳过与该工具相关的那一条检查。

这里不为上游 DOM 输出写 contract（那是 Phase 3/4 的职责），也不触碰 renderer 契约。
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = ROOT / "upstream" / "pin.json"
GITMODULES_PATH = ROOT / ".gitmodules"
SUBMODULE_PATH = ROOT / "upstream" / "vscode-office"
UPDATE_SCRIPT = ROOT / "tools" / "update_vscode_office.ps1"

GITLINK_MODE = "160000"
GITLINK_PATH = "upstream/vscode-office"
SUBMODULE_HINT = "上游 submodule 未初始化；请执行：git submodule update --init --recursive"

REQUIRED_PIN_KEYS = (
    "schema",
    "repo",
    "path",
    "default_branch",
    "pinned_commit",
    "commit_date",
    "commit_subject",
    "package_version",
    "license",
    "recorded_at",
    "recorded_by_phase",
    "fact_sources",
    "why_this_commit",
    "verify",
    "capabilities",
)


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
        pytest.skip("git 不在 PATH 上（平台工具缺失）：只跳过依赖 git 的上游检查。")


def _require_pwsh() -> None:
    if shutil.which("pwsh") is None:
        pytest.skip("pwsh 不在 PATH 上（平台工具缺失）：只跳过上游更新脚本的检查。")


def _pin() -> dict:
    assert PIN_PATH.is_file(), "upstream/pin.json 缺失：这是 Phase 2 的必需仓库状态"
    return json.loads(PIN_PATH.read_text(encoding="utf-8"))


def _gitlink_entry():
    """返回 superproject 索引里记录的 (mode, commit)；没有条目则 None。"""
    completed = _git(["ls-files", "-s", GITLINK_PATH], ROOT)
    if completed.returncode != 0:
        return None
    parts = completed.stdout.split()
    if len(parts) < 4:
        return None
    return parts[0], parts[1]


def _checkout_commit():
    if not (SUBMODULE_PATH / ".git").exists():
        return None
    completed = _git(["rev-parse", "HEAD"], SUBMODULE_PATH)
    if completed.returncode != 0:
        return None
    commit = completed.stdout.strip()
    return commit or None


def _require_checkout() -> str:
    commit = _checkout_commit()
    if commit is None:
        pytest.fail(SUBMODULE_HINT)
    return commit


def _parse_gitmodules() -> dict:
    entries: dict = {}
    current = None
    for line in GITMODULES_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("[submodule "):
            current = stripped[len("[submodule ") :].rstrip("]").strip().strip('"')
            entries[current] = {}
        elif current and "=" in stripped:
            key, _, value = stripped.partition("=")
            entries[current][key.strip()] = value.strip()
    return entries


def _run_update_script(*args: str) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        [shutil.which("pwsh"), "-NoProfile", "-File", str(UPDATE_SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    completed.output = (completed.stdout or "") + (completed.stderr or "")
    return completed


def test_gitmodules_is_the_upstream_location_source():
    _require_git()
    pin = _pin()
    assert GITMODULES_PATH.is_file(), ".gitmodules 缺失：upstream 仓库位置没有来源"
    entries = _parse_gitmodules()

    assert list(entries) == [pin["path"]]
    assert entries[pin["path"]]["path"] == pin["path"]
    assert entries[pin["path"]]["url"] == pin["repo"]


def test_gitlink_is_the_authoritative_pinned_commit():
    _require_git()
    pin = _pin()
    entry = _gitlink_entry()

    assert entry is not None, "superproject 索引里没有 upstream/vscode-office 的 gitlink"
    assert entry[0] == GITLINK_MODE
    assert entry[1] == pin["pinned_commit"]


def test_upstream_checkout_matches_the_pinned_commit():
    _require_git()
    pin = _pin()

    assert _require_checkout() == pin["pinned_commit"]


def test_pin_manifest_agrees_with_gitlink_and_checkout():
    _require_git()
    pin = _pin()
    entry = _gitlink_entry()

    assert entry is not None, "superproject 索引里没有 upstream/vscode-office 的 gitlink"
    assert {entry[1], _require_checkout()} == {pin["pinned_commit"]}


def test_upstream_worktree_has_no_local_modifications():
    _require_git()
    _require_checkout()

    completed = _git(["status", "--porcelain"], SUBMODULE_PATH)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "", completed.stdout


def test_pin_record_is_complete():
    pin = _pin()

    for key in REQUIRED_PIN_KEYS:
        assert key in pin, key
    assert pin["schema"] == 1
    assert len(pin["pinned_commit"]) == 40
    assert pin["recorded_by_phase"] == "Phase 2"
    assert pin["verify"]["paths"]
    assert pin["verify"]["dependencies"]
    assert pin["fact_sources"]["pinned_commit"], "必须写明 pinned commit 的权威来源"

    capabilities = pin["capabilities"]
    assert capabilities
    ids = [entry["id"] for entry in capabilities]
    assert len(set(ids)) == len(ids), ids
    for entry in capabilities:
        if entry["present"] is False:
            assert entry.get("reason"), entry["id"]
        else:
            assert entry["evidence"], entry["id"]


def test_recorded_capability_evidence_exists_in_the_checkout():
    _require_git()
    _require_checkout()
    pin = _pin()

    missing = [
        relative for relative in pin["verify"]["paths"] if not (SUBMODULE_PATH / relative).exists()
    ]
    assert missing == [], missing

    for entry in pin["capabilities"]:
        for relative in entry["evidence"]:
            assert (SUBMODULE_PATH / relative).exists(), (entry["id"], relative)

    package = json.loads((SUBMODULE_PATH / "package.json").read_text(encoding="utf-8"))
    dependencies = package.get("dependencies", {})
    for name, expected in pin["verify"]["dependencies"].items():
        assert dependencies.get(name) == expected, (name, dependencies.get(name))
    for name in pin["verify"]["absent_dependencies"]:
        assert name not in dependencies, name


def test_update_script_reports_a_missing_checkout(tmp_path: Path):
    _require_pwsh()

    no_repo = tmp_path / "no-repo"
    no_repo.mkdir()
    completed = _run_update_script("-RepoRoot", str(no_repo))
    assert completed.returncode != 0, completed.output
    assert "RESULT: ERROR" in completed.output
    assert ".gitmodules" in completed.output
    assert "git submodule add" in completed.output

    no_checkout = tmp_path / "no-checkout"
    (no_checkout / "upstream").mkdir(parents=True)
    (no_checkout / ".gitmodules").write_text(
        '[submodule "upstream/vscode-office"]\n'
        "\tpath = upstream/vscode-office\n"
        "\turl = https://github.com/cweijan/vscode-office.git\n",
        encoding="utf-8",
    )
    (no_checkout / "upstream" / "pin.json").write_text(
        PIN_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    completed = _run_update_script("-RepoRoot", str(no_checkout))
    assert completed.returncode != 0, completed.output
    assert "RESULT: ERROR" in completed.output
    assert "submodule update --init" in completed.output


def test_update_script_check_mode_prints_the_pinned_commit():
    _require_pwsh()
    _require_checkout()

    completed = _run_update_script("-Check")

    assert completed.returncode == 0, completed.output
    assert "RESULT: OK" in completed.output
    assert _pin()["pinned_commit"] in completed.output
    assert _checkout_commit() == _pin()["pinned_commit"]
    assert _git(["status", "--porcelain"], SUBMODULE_PATH).stdout.strip() == ""


def test_update_script_rejects_a_wrong_expected_commit():
    _require_pwsh()
    _require_checkout()

    completed = _run_update_script("-ExpectCommit", "0" * 40)

    assert completed.returncode != 0, completed.output
    assert "RESULT: ERROR" in completed.output
    assert "0" * 40 in completed.output
    assert _pin()["pinned_commit"] in completed.output
