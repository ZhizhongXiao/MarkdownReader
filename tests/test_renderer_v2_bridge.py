"""Cutover C2：Python production bridge 的 v2 调用契约（K26）。

三类覆盖：

  * 真实调用：真实 Node + 真实 `renderer/dist/renderer.cjs`，断言完整 envelope 与各通道原样透传；
  * 协议与形状拒绝：patch `renderer_v2._invoke_artifact` 注入 stdout，不依赖 renderer 真的出错；
  * 反证：artifact 缺失时**不回退 v1**（v1 helper 一旦被调用即 AssertionError）。

Node 版本下限与 runtime policy 归 `tests/test_node_runtime.py`；这里只管调用与 envelope。
"""

import base64
import json
import sys
from pathlib import Path

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
    """每个用例都从「未验证」开始，v1 的缓存也一并隔离。"""
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
    """K26：显式选择 v2 后失败就失败，绝不偷偷跑 v1。"""
    monkeypatch.setattr(renderer_v2, "ARTIFACT", str(tmp_path / "missing" / "renderer.cjs"))

    def forbidden(*args, **kwargs):
        raise AssertionError("v2 失败时不得回退到 v1")

    monkeypatch.setattr(renderer_node, "_render_markdown_v1", forbidden)

    with pytest.raises(RuntimeError) as error:
        renderer_node.render_markdown_node("# x", renderer_version="v2")

    message = str(error.value)
    assert "构建产物缺失" in message
    assert "npm run build" in message
    assert "不会回退" in message


def test_a_non_v2_protocol_response_is_refused(monkeypatch, node_command):
    _patch_stdout(monkeypatch, json.dumps({"protocol_version": 1, "ok": True}))

    with pytest.raises(RuntimeError) as error:
        renderer_node.render_markdown_node("# x", renderer_version="v2")

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
        renderer_node.render_markdown_node("# x", renderer_version="v2")

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
        renderer_node.render_markdown_node("# x", renderer_version="v2")

    message = str(error.value)
    assert "invalid_json" in message
    assert "请求不是合法 JSON。" in message
    assert "line 1" in message


@pytest.mark.parametrize("stdout", ["", "not json at all", "[1, 2, 3]", '"a string"'])
def test_a_stdout_that_is_not_one_envelope_is_refused(monkeypatch, node_command, stdout):
    _patch_stdout(monkeypatch, stdout)

    with pytest.raises(RuntimeError):
        renderer_node.render_markdown_node("# x", renderer_version="v2")


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
        renderer_node.render_markdown_node("# x", renderer_version="v2")

    assert "author_references" in str(error.value)


def test_the_v2_runtime_is_validated_once_per_process(monkeypatch, node_command):
    calls = []
    original = renderer_v2._invoke_artifact

    def counting(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(renderer_v2, "_invoke_artifact", counting)

    renderer_node.render_markdown_node("# one\n", renderer_version="v2", options=OFFLINE)
    renderer_node.render_markdown_node("# two\n", renderer_version="v2", options=OFFLINE)

    assert len(calls) == 3, "一次冒烟 + 两次真实渲染"
    assert renderer_v2.validate_v2_runtime(node_command), "已缓存的运行时直接返回"
    assert len(calls) == 3, "已缓存的运行时不再冒烟"


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
