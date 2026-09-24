"""新 renderer 的协议契约（Phase 3 建立 v1，Phase 5A 起为 v2：resources 是必在字段）。

证明 adapter 的 JSON 契约本身稳定、可诊断、可独立运行；Markdown 语义对照在
 test_renderer_adapter_keep.py。产物缺失 = 明确失败 + 构建提示；缺 node = 平台工具缺失才 skip。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from renderer_adapter import (  # noqa: E402
    PIN_MANIFEST,
    RENDERER_DIR,
    UPSTREAM_SUBMODULE,
    render,
    require_artifact,
    require_node,
    run_adapter,
)

PROTOCOL_VERSION = 2
FEATURE_KEYS = (
    "katex",
    "mermaid",
    "plantuml",
    "checkbox",
    "callout",
    "wikilink",
    "mark",
    "obsidian_tag",
)

SAMPLE = "# 标题\n\n正文段落。\n"


def test_build_artifact_is_present():
    require_artifact()


def test_protocol_version_and_ok_flag():
    envelope = render(SAMPLE)

    assert envelope["protocol_version"] == PROTOCOL_VERSION
    assert envelope["ok"] is True


def test_stdout_is_exactly_one_json_object():
    completed = run_adapter({"markdown": SAMPLE})

    assert completed.returncode == 0, completed.stderr
    stripped = completed.stdout.strip()
    assert stripped.startswith("{") and stripped.endswith("}"), stripped[:200]
    json.loads(stripped)
    assert "\n" not in stripped, "stdout 必须是单行 JSON：日志与诊断不能混进来"


def test_required_keys_and_types():
    envelope = render(SAMPLE)

    for key in ("protocol_version", "ok", "html", "headings", "features", "warnings", "resources"):
        assert key in envelope, key
    assert isinstance(envelope["html"], str) and envelope["html"]
    assert isinstance(envelope["headings"], list)
    assert isinstance(envelope["features"], dict)
    assert isinstance(envelope["warnings"], list)
    # v2：resources 必在；资源细节契约见 tests/test_renderer_adapter_resources.py。
    assert set(envelope["resources"]) == {"items", "styles"}
    assert isinstance(envelope["resources"]["items"], list)
    assert isinstance(envelope["resources"]["styles"], list)


def test_features_schema_is_complete_and_boolean():
    envelope = render(SAMPLE)

    assert set(envelope["features"]) == set(FEATURE_KEYS)
    assert all(isinstance(value, bool) for value in envelope["features"].values())


def test_headings_schema_follows_the_adapter_contract():
    envelope = render("# 一\n\n## 二\n\n### 三\n")
    headings = envelope["headings"]

    assert [heading["level"] for heading in headings] == [1, 2, 3]
    assert [heading["text"] for heading in headings] == ["一", "二", "三"]
    for heading in headings:
        assert set(heading) == {"level", "text", "anchor", "inline_html", "toc_inline_html"}
        assert heading["anchor"]


def test_malformed_json_yields_an_error_envelope():
    completed = run_adapter("not json")

    assert completed.returncode != 0
    envelope = json.loads(completed.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "invalid_json"
    assert envelope["protocol_version"] == PROTOCOL_VERSION
    assert completed.stderr.strip(), "诊断必须出现在 stderr"


def test_missing_markdown_field_yields_an_error_envelope():
    completed = run_adapter({"options": {}})

    assert completed.returncode != 0
    envelope = json.loads(completed.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "invalid_request"


def test_empty_stdin_yields_an_error_envelope():
    completed = run_adapter("")

    assert completed.returncode != 0
    assert json.loads(completed.stdout)["error"]["code"] == "input_empty"


def test_info_mode_reports_protocol_and_reused_upstream_sources():
    completed = run_adapter("", args=("--info",))

    assert completed.returncode == 0, completed.stderr
    info = json.loads(completed.stdout)
    assert info["protocol_version"] == PROTOCOL_VERSION
    assert info["missing_sources"] == []
    assert info["reused_sources"], "必须报告实际复用的上游源文件"
    for relative in info["reused_sources"]:
        assert (UPSTREAM_SUBMODULE / relative).is_file(), relative
    pin = json.loads(PIN_MANIFEST.read_text(encoding="utf-8"))
    assert info["pinned_commit"] == pin["pinned_commit"]


def test_build_leaves_upstream_pristine():
    node = require_node()
    require_artifact()
    if not (RENDERER_DIR / "node_modules").is_dir():
        pytest.fail("renderer/node_modules 缺失：请先执行 cd renderer; npm ci")

    completed = subprocess.run(
        [node, str(RENDERER_DIR / "build" / "build.js")],
        cwd=str(RENDERER_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert completed.returncode == 0, completed.stderr
    if not (UPSTREAM_SUBMODULE / ".git").exists():
        pytest.fail("上游 submodule 未初始化：git submodule update --init --recursive")
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(UPSTREAM_SUBMODULE),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert status.stdout.strip() == "", status.stdout
