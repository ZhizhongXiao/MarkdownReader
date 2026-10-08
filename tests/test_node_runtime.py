"""Node runtime ownership and v2 renderer validation contracts."""

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import renderer_node, renderer_v2  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_runtime_cache(monkeypatch):
    renderer_v2.close_renderer_session()
    monkeypatch.setattr(renderer_node, "_RESOLVED_NODE", None)
    monkeypatch.setattr(renderer_node, "_RESOLVED_NODE_VERSION", None)
    yield
    renderer_v2.close_renderer_session()


def _completed(args, stdout):
    return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")


def test_startup_preflight_checks_node_and_artifact_once_per_process(monkeypatch):
    probes = []
    artifact_checks = []

    def fake_run(args, **kwargs):
        probes.append(list(args))
        return _completed(args, "v22.0.0")

    def require_artifact():
        artifact_checks.append(True)
        return "renderer.cjs"

    monkeypatch.setattr(renderer_node.subprocess, "run", fake_run)
    monkeypatch.setattr(renderer_node, "resolve_node_runtime", lambda: "node")
    monkeypatch.setattr(renderer_v2, "require_artifact", require_artifact)

    first = renderer_node.validate_renderer_runtime()
    second = renderer_node.validate_renderer_runtime()

    assert first == second == "node"
    assert probes == [["node", "--version"]]
    assert artifact_checks == [True]


def test_the_bridge_uses_v2_and_preserves_offline_defaults(monkeypatch):
    calls = []
    monkeypatch.setattr(renderer_node, "validate_renderer_runtime", lambda: "bundled-node")

    def render_v2(node_command, markdown, context, options):
        calls.append((node_command, markdown, context, options))
        return {"protocol_version": 2, "ok": True}

    monkeypatch.setattr(renderer_v2, "render_markdown_v2", render_v2)

    result = renderer_node.render_markdown_node("# 标题", {"source_path": "doc.md"})

    assert result["protocol_version"] == 2
    assert calls == [
        (
            "bundled-node",
            "# 标题",
            {"source_path": "doc.md"},
            {"fetch_remote_resources": False},
        )
    ]


def test_an_explicit_renderer_version_selector_does_not_exist():
    parameters = inspect.signature(renderer_node.render_markdown_node).parameters
    assert "renderer_version" not in parameters


def test_a_packaged_build_refuses_to_borrow_node_from_path(monkeypatch, tmp_path):
    monkeypatch.setattr(renderer_node, "_BUNDLED_NODE", str(tmp_path / "missing" / "node.exe"))
    monkeypatch.setattr(renderer_node, "_is_frozen", lambda: True)
    with pytest.raises(RuntimeError) as error:
        renderer_node.resolve_node_runtime()
    assert "打包物损坏" in str(error.value)


def test_a_source_checkout_may_use_path(monkeypatch, tmp_path):
    monkeypatch.setattr(renderer_node, "_BUNDLED_NODE", str(tmp_path / "missing" / "node.exe"))
    monkeypatch.setattr(renderer_node, "_is_frozen", lambda: False)
    assert renderer_node.resolve_node_runtime() == "node"


def test_a_failing_first_render_does_not_cache_runtime_validation(monkeypatch):
    monkeypatch.setattr(renderer_node, "resolve_node_runtime", lambda: "node")
    monkeypatch.setattr(
        renderer_node.subprocess,
        "run",
        lambda args, **kwargs: _completed(args, "v22.0.0"),
    )

    def fail_smoke(*_args, **kwargs):
        assert kwargs["runtime_validation"] is True
        raise RuntimeError("smoke failed")

    monkeypatch.setattr(renderer_v2, "require_artifact", lambda: "renderer.cjs")
    monkeypatch.setattr(renderer_v2.RendererSession, "start", lambda _self: 1)
    monkeypatch.setattr(renderer_v2, "_invoke_artifact", fail_smoke)
    with pytest.raises(RuntimeError, match="smoke failed"):
        renderer_node.render_markdown_node("# first request")
    assert renderer_v2._DEFAULT_BRIDGE._validated_generation is None


def test_the_version_probe_is_read_once(monkeypatch):
    probes = []

    def fake_run(args, **kwargs):
        probes.append(list(args))
        return _completed(args, "v24.20.0")

    monkeypatch.setattr(renderer_node.subprocess, "run", fake_run)
    assert renderer_node.probe_node_version("node") == "v24.20.0"
    assert renderer_node.probe_node_version("node") == "v24.20.0"
    assert probes == [["node", "--version"]]


def test_the_v2_floor_rejects_old_node_before_runtime_validation(monkeypatch):
    monkeypatch.setattr(renderer_node, "resolve_node_runtime", lambda: "node")
    monkeypatch.setattr(
        renderer_node.subprocess,
        "run",
        lambda args, **kwargs: _completed(args, "v17.9.0"),
    )

    def forbidden():
        raise AssertionError("artifact check must follow the version floor")

    monkeypatch.setattr(renderer_v2, "require_artifact", forbidden)
    with pytest.raises(RuntimeError) as error:
        renderer_node.validate_renderer_runtime()
    assert "major >= 18" in str(error.value)
    assert "v17.9.0" in str(error.value)


def test_the_v2_floor_accepts_node_18_and_newer():
    assert renderer_node._require_v2_node_major("v18.0.0") == 18
    assert renderer_node._require_v2_node_major("v24.20.0") == 24
    assert renderer_v2.MINIMUM_NODE_MAJOR == 18


def test_an_unparseable_node_version_is_refused(monkeypatch):
    monkeypatch.setattr(renderer_node, "resolve_node_runtime", lambda: "node")
    monkeypatch.setattr(
        renderer_node.subprocess,
        "run",
        lambda args, **kwargs: _completed(args, "not-a-version"),
    )
    monkeypatch.setattr(
        renderer_v2,
        "require_artifact",
        lambda: pytest.fail("invalid version must be rejected first"),
    )

    with pytest.raises(RuntimeError) as error:
        renderer_node.validate_renderer_runtime()
    assert "无法解析 Node 版本" in str(error.value)
