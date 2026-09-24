"""上游 vscode-office pin 契约（Phase 2）。

这些检查只证明接入本身是可复现、可追踪、未被改动的：

  * .gitmodules 与 upstream/pin.json 指向同一个仓库与路径；
  * checkout 停在 pin 的 commit（不跟随 main）；
  * 上游工作区没有本地修改 —— MarkdownReader 不 patch 上游；
  * pin 记录里的证据路径与依赖版本在 checkout 中真实存在，能力声明可核验而不是散文；
  * 检查脚本对错误状态给出可读错误，并且不依赖本机手工复制目录。

这里不为上游 DOM 输出写 contract（那是 Phase 3/4 的职责），也不触碰 renderer 契约。
submodule 未初始化、缺 git 或缺 pwsh 时显式 skip 并说明原因，绝不静默通过。
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
    "why_this_commit",
    "verify",
    "capabilities",
)


def _pin() -> dict:
    return json.loads(PIN_PATH.read_text(encoding="utf-8"))


def _git(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _submodule_commit():
    if not (SUBMODULE_PATH / ".git").exists():
        return None
    completed = _git(["rev-parse", "HEAD"], SUBMODULE_PATH)
    if completed.returncode != 0:
        return None
    commit = completed.stdout.strip()
    return commit or None


def _submodule_skip_reason() -> str:
    if shutil.which("git") is None:
        return "git 不在 PATH 上，无法检查上游 checkout。"
    if not (SUBMODULE_PATH / ".git").exists():
        return "上游 submodule 未初始化；请执行：git submodule update --init --recursive"
    if _submodule_commit() is None:
        return "无法读取上游 checkout 的 commit（git rev-parse 失败）。"
    return ""


def _require_submodule() -> str:
    reason = _submodule_skip_reason()
    if reason:
        pytest.skip(reason)
    commit = _submodule_commit()
    assert commit
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


def test_gitmodules_declares_the_upstream_submodule():
    pin = _pin()
    assert GITMODULES_PATH.is_file(), ".gitmodules 缺失"
    entries = _parse_gitmodules()

    assert list(entries) == [pin["path"]]
    assert entries[pin["path"]]["path"] == pin["path"]
    assert entries[pin["path"]]["url"] == pin["repo"]


def test_upstream_checkout_is_initialised_at_the_pinned_commit():
    commit = _require_submodule()

    assert commit == _pin()["pinned_commit"]


def test_upstream_worktree_has_no_local_modifications():
    _require_submodule()

    completed = _git(["status", "--porcelain"], SUBMODULE_PATH)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "", completed.stdout


def test_pin_record_is_complete():
    pin = _pin()

    for key in REQUIRED_PIN_KEYS:
        assert key in pin, key
    assert pin["schema"] == 1
    assert pin["pinned_commit"] and len(pin["pinned_commit"]) == 40
    assert pin["recorded_by_phase"] == "Phase 2"
    assert pin["verify"]["paths"]
    assert pin["verify"]["dependencies"]

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
    _require_submodule()
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
    if shutil.which("pwsh") is None:
        pytest.skip("pwsh 不在 PATH 上，无法运行上游更新脚本。")

    # 1) 完全没有接入：临时目录里没有 .gitmodules
    no_repo = tmp_path / "no-repo"
    no_repo.mkdir()
    completed = _run_update_script("-RepoRoot", str(no_repo))
    assert completed.returncode != 0, completed.output
    assert "RESULT: ERROR" in completed.output
    assert ".gitmodules" in completed.output
    assert "git submodule add" in completed.output

    # 2) 有 .gitmodules 与 pin 记录，但没有已初始化的 checkout：必须提示 init 命令
    no_checkout = tmp_path / "no-checkout"
    (no_checkout / "upstream").mkdir(parents=True)
    (no_checkout / ".gitmodules").write_text(
        "[submodule \"upstream/vscode-office\"]\n"
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
    _require_submodule()
    if shutil.which("pwsh") is None:
        pytest.skip("pwsh 不在 PATH 上，无法运行上游更新脚本。")

    completed = _run_update_script("-Check")

    assert completed.returncode == 0, completed.output
    assert "RESULT: OK" in completed.output
    assert _pin()["pinned_commit"] in completed.output
    assert _submodule_commit() == _pin()["pinned_commit"]
    assert _git(["status", "--porcelain"], SUBMODULE_PATH).stdout.strip() == ""


def test_update_script_rejects_a_wrong_expected_commit():
    _require_submodule()
    if shutil.which("pwsh") is None:
        pytest.skip("pwsh 不在 PATH 上，无法运行上游更新脚本。")

    completed = _run_update_script("-ExpectCommit", "0" * 40)

    assert completed.returncode != 0, completed.output
    assert "RESULT: ERROR" in completed.output
    assert "0" * 40 in completed.output
    assert _pin()["pinned_commit"] in completed.output
