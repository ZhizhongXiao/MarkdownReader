"""Cutover C2：Python production bridge 的 v2 调用契约（K26）。

三类覆盖：

  * 真实调用：真实 Node + 真实 `renderer/dist/renderer.cjs`，断言完整 envelope 与各通道原样透传；
  * 协议与形状拒绝：patch `renderer_v2._invoke_artifact` 注入 stdout，不依赖 renderer 真的出错；
  * artifact 缺失时给出可执行的 v2 构建提示。

Node 版本下限与 runtime policy 归 `tests/test_node_runtime.py`；这里只管调用与 envelope。
"""

import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from renderer_adapter import require_node  # noqa: E402

from core import renderer_node, renderer_v2  # noqa: E402

# 与 tests/test_renderer_adapter_resources.py 一致的 1x1 PNG。
MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)
OFFLINE = {"fetch_remote_resources": False}


@pytest.fixture(autouse=True)
def _fresh_caches(monkeypatch):
    """每个用例都从「未验证」开始。"""
    monkeypatch.setattr(renderer_v2, "_VALIDATED_RUNTIME", None)
    monkeypatch.setattr(renderer_node, "_RESOLVED_NODE", None)
    monkeypatch.setattr(renderer_node, "_RESOLVED_NODE_VERSION", None)


@pytest.fixture
def node_command():
    return require_node()


def _patch_stdout(monkeypatch, stdout):
    """Replace the artifact call with a fixed stdout (the renderer never runs)."""
    monkeypatch.setattr(renderer_v2, "_invoke_artifact", lambda *args, **kwargs: stdout)


def test_the_v2_envelope_is_complete(node_command):
    envelope = renderer_v2.render_markdown_v2(node_command, "# 标题\n\n公式 $a^2$。\n", {}, OFFLINE)

    assert envelope["protocol_version"] == 2
    assert envelope["ok"] is True
    for key in ("html", "headings", "features", "warnings", "resources"):
        assert key in envelope, key
    assert set(envelope["resources"]) == {"items", "styles", "scripts", "author_references"}
    assert envelope["html"]
    assert "标题" in json.dumps(envelope["headings"], ensure_ascii=False)
    assert envelope["features"]["katex"] is True


def test_every_channel_survives_the_bridge(tmp_path, node_command):
    """C1 的 provenance 与 5A/5B 的 items/styles/scripts 必须原样到达 Python。"""
    (tmp_path / "pic.png").write_bytes(MINIMAL_PNG)
    markdown = (
        "![本地](pic.png)\n\n"
        "```mermaid\ngraph TD; A-->B;\n```\n\n"
        "公式 $a^2$。\n\n"
        '<img src="https://raw.invalid/a.png">\n'
    )

    envelope = renderer_v2.render_markdown_v2(
        node_command, markdown, {"source_path": str(tmp_path / "doc.md")}, OFFLINE
    )

    resources = envelope["resources"]
    images = [item for item in resources["items"] if item["kind"] == "image"]
    assert [item["ref"] for item in images] == ["pic.png"]
    assert images[0]["status"] == "inlined"
    assert [style["id"] for style in resources["styles"]] == ["katex"]
    assert [script["id"] for script in resources["scripts"]] == ["mermaid"]
    assert resources["author_references"] == [{"ref": "https://raw.invalid/a.png", "count": 1}]


def test_a_missing_artifact_fails_actionably_and_never_falls_back(monkeypatch, tmp_path):
    """缺少 v2 artifact 时应给出 actionable failure。"""
    monkeypatch.setattr(renderer_v2, "ARTIFACT", str(tmp_path / "missing" / "renderer.cjs"))

    with pytest.raises(RuntimeError) as error:
        renderer_node.render_markdown_node("# x")

    message = str(error.value)
    assert "构建产物缺失" in message
    assert "npm run build" in message
    assert str(tmp_path / "missing" / "renderer.cjs") in message


def test_a_non_v2_protocol_response_is_refused(monkeypatch, node_command):
    _patch_stdout(monkeypatch, json.dumps({"protocol_version": 1, "ok": True}))

    with pytest.raises(RuntimeError) as error:
        renderer_node.render_markdown_node("# x")

    assert "protocol_version" in str(error.value)


def test_a_missing_protocol_version_is_refused(monkeypatch, node_command):
    _patch_stdout(
        monkeypatch,
        json.dumps(
            {
                "ok": True,
                "html": "<p>x</p>",
                "headings": [],
                "features": {},
                "warnings": [],
                "resources": {},
            }
        ),
    )

    with pytest.raises(RuntimeError) as error:
        renderer_node.render_markdown_node("# x")

    assert "protocol_version" in str(error.value)


def test_an_error_envelope_becomes_a_readable_python_error(monkeypatch, node_command):
    _patch_stdout(
        monkeypatch,
        json.dumps(
            {
                "protocol_version": 2,
                "ok": False,
                "error": {
                    "code": "invalid_json",
                    "message": "请求不是合法 JSON。",
                    "detail": "line 1",
                },
            }
        ),
    )

    with pytest.raises(RuntimeError) as error:
        renderer_node.render_markdown_node("# x")

    message = str(error.value)
    assert "invalid_json" in message
    assert "请求不是合法 JSON。" in message
    assert "line 1" in message


@pytest.mark.parametrize("stdout", ["", "not json at all", "[1, 2, 3]", '"a string"'])
def test_a_stdout_that_is_not_one_envelope_is_refused(monkeypatch, node_command, stdout):
    _patch_stdout(monkeypatch, stdout)

    with pytest.raises(RuntimeError):
        renderer_node.render_markdown_node("# x")


def test_a_missing_channel_is_refused(monkeypatch, node_command):
    """v2 的必在形状是契约：少了 author_references 就是失败，而不是「为空」。"""
    _patch_stdout(
        monkeypatch,
        json.dumps(
            {
                "protocol_version": 2,
                "ok": True,
                "html": "<p>x</p>",
                "headings": [],
                "features": {},
                "warnings": [],
                "resources": {"items": [], "styles": [], "scripts": []},
            }
        ),
    )

    with pytest.raises(RuntimeError) as error:
        renderer_node.render_markdown_node("# x")

    assert "author_references" in str(error.value)


def test_the_v2_runtime_is_validated_once_per_process(monkeypatch, node_command):
    calls = []
    original = renderer_v2._invoke_artifact

    def counting(*args, **kwargs):
        calls.append(kwargs.get("runtime_validation", False))
        return original(*args, **kwargs)

    monkeypatch.setattr(renderer_v2, "_invoke_artifact", counting)

    first = renderer_node.render_markdown_node("# one\n", options=OFFLINE)
    renderer_node.render_markdown_node("# two\n", options=OFFLINE)

    assert calls == [True, False], "首次真实请求合并 smoke；后续请求不再校验"
    assert set(first) == {
        "protocol_version",
        "ok",
        "html",
        "headings",
        "features",
        "warnings",
        "resources",
    }, "runtime smoke 附加字段不得流入生产 envelope"
    validated_runtime = renderer_v2._VALIDATED_RUNTIME
    resolved_runtime = renderer_node.validate_renderer_runtime()
    assert validated_runtime == resolved_runtime


def test_first_request_carries_offline_smoke_and_unwraps_the_v2_envelope(monkeypatch):
    calls = []
    actual = {
        "protocol_version": 2,
        "ok": True,
        "html": "<p>actual</p>",
        "headings": [],
        "features": {},
        "warnings": [],
        "resources": {"items": [], "styles": [], "scripts": [], "author_references": []},
    }
    smoke = {
        "protocol_version": 2,
        "ok": True,
        "html": '<span class="katex">formula</span>',
        "headings": [],
        "features": {"katex": True},
        "warnings": [],
        "resources": {
            "items": [],
            "styles": [{"id": "katex", "css": ""}],
            "scripts": [],
            "author_references": [],
        },
    }

    def fake_run(args, **kwargs):
        calls.append(json.loads(kwargs["input"]))
        response = dict(actual, runtime_validation=smoke)
        return SimpleNamespace(returncode=0, stdout=json.dumps(response), stderr="")

    monkeypatch.setattr(renderer_v2.subprocess, "run", fake_run)

    envelope = renderer_v2.render_markdown_v2(
        "node", "# actual", {}, {"fetch_remote_resources": True}
    )

    assert len(calls) == 1
    assert calls[0]["runtime_validation"] == {
        "markdown": renderer_v2.SMOKE_MARKDOWN,
        "options": {"fetch_remote_resources": False, "math": True},
        "context": {},
    }
    assert calls[0]["options"] == {"fetch_remote_resources": True}
    assert set(envelope) == set(actual)
    assert envelope["html"] == "<p>actual</p>"


def test_the_v2_smoke_is_offline_and_proves_katex(node_command):
    """冒烟输入来自模块常量：显式关网，并要求 dist/katex 真的参与渲染。"""
    assert renderer_v2.SMOKE_OPTIONS["fetch_remote_resources"] is False

    envelope = renderer_v2.render_markdown_v2(
        node_command, renderer_v2.SMOKE_MARKDOWN, {}, renderer_v2.SMOKE_OPTIONS
    )

    assert 'class="katex"' in envelope["html"]
    assert [style["id"] for style in envelope["resources"]["styles"]] == ["katex"]
    assert envelope["resources"]["author_references"] == []
    assert envelope["warnings"] == []
