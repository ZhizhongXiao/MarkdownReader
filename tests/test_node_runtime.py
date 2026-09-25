"""Node runtime ownership: validated once per process, never silently borrowed.

Node and the renderer assets belong to the MarkdownReader runtime rather than to
an individual conversion job. These cases lock that shape: the runtime is probed
once per process, a render reuses the answer, and a packaged build refuses to
borrow a Node from PATH, because that would hide a broken package until it
reaches a machine where Node happens to be missing.
"""

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
    monkeypatch.setattr(renderer_node, "_RESOLVED_NODE", None)
    monkeypatch.setattr(renderer_node, "_RESOLVED_NODE_VERSION", None)


def _completed(args, stdout):
    return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")


def test_runtime_is_validated_once_per_process(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        argv = list(args)
        calls.append(argv)
        if argv[1] == "--version":
            return _completed(args, "v22.0.0")
        return _completed(args, "{\"html\": \"<p>x</p>\", \"headings\": [], \"warnings\": []}")

    monkeypatch.setattr(renderer_node.subprocess, "run", fake_run)
    first = renderer_node.validate_renderer_runtime()
    second = renderer_node.validate_renderer_runtime()
    assert first == second
    assert len(calls) == 2, "one version probe and one smoke render, then nothing"
    assert calls[0][1] == "--version"
    assert calls[1][1] == renderer_node._RENDER_JS


def test_a_render_reuses_the_validated_runtime(monkeypatch):
    probes = []
    renders = []

    def fake_run(args, **kwargs):
        argv = list(args)
        if argv[1] == "--version":
            probes.append(argv)
            return _completed(args, "v22.0.0")
        renders.append(argv)
        return _completed(args, '{"html": "<p>x</p>", "headings": [], "warnings": []}')

    monkeypatch.setattr(renderer_node.subprocess, "run", fake_run)
    renderer_node.render_markdown_node("# one")
    renderer_node.render_markdown_node("# two")
    assert len(probes) == 1, "two renders must not probe Node twice"
    # The smoke render happens once during validation, then the two real renders.
    assert len(renders) == 3


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


def test_a_failing_smoke_fails_validation(monkeypatch):
    """A renderer that cannot render must not be remembered as usable."""

    def fake_run(args, **kwargs):
        if list(args)[1] == "--version":
            return _completed(args, "v22.0.0")
        return _completed(args, "not json at all")

    monkeypatch.setattr(renderer_node.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        renderer_node.validate_renderer_runtime()
    assert renderer_node._RESOLVED_NODE is None, "a failed check must not be cached"


# --- Cutover C2：显式 v1 / v2 选择与 v2 的 Node 能力下限（K26） -------------------------

_V1_PAYLOAD = '{"html": "<p>x</p>", "headings": [], "warnings": []}'


def _fake_node_run(version, payload=_V1_PAYLOAD):
    """Fake `subprocess.run` for the version probe and the render call."""

    def fake_run(args, **kwargs):
        if list(args)[1] == "--version":
            return _completed(args, version)
        return _completed(args, payload)

    return fake_run


def _forbidden(*args, **kwargs):
    raise AssertionError("v1 路径不得触碰 v2 桥")


def test_the_version_probe_is_shared_and_reads_node_once(monkeypatch):
    """v1 的运行时校验与 v2 的下限判定共用同一个探针与缓存。"""
    probes = []

    def fake_run(args, **kwargs):
        if list(args)[1] == "--version":
            probes.append(list(args))
            return _completed(args, "v24.20.0")
        return _completed(args, _V1_PAYLOAD)

    monkeypatch.setattr(renderer_node.subprocess, "run", fake_run)
    assert renderer_node.probe_node_version("node") == "v24.20.0"
    renderer_node.validate_renderer_runtime()
    assert renderer_node.probe_node_version("node") == "v24.20.0"
    assert len(probes) == 1, "Node 版本每进程只读一次"


def test_v2_selection_enforces_the_node_floor_before_touching_the_bridge(monkeypatch):
    monkeypatch.setattr(renderer_node.subprocess, "run", _fake_node_run("v17.9.0"))
    monkeypatch.setattr(renderer_v2, "validate_v2_runtime", _forbidden)

    with pytest.raises(RuntimeError) as error:
        renderer_node.render_markdown_node("# x", renderer_version="v2")

    message = str(error.value)
    assert "major >= 18" in message and "v17.9.0" in message


def test_the_v2_floor_accepts_node_18_and_newer():
    assert renderer_node._require_v2_node_major("v18.0.0") == 18
    assert renderer_node._require_v2_node_major("v24.20.0") == 24
    # 打包门禁也读这个常量（packaging/MarkdownReader.spec），改它等于改发布下限。
    assert renderer_v2.MINIMUM_NODE_MAJOR == 18


def test_an_unparseable_node_version_is_refused(monkeypatch):
    """拿不到版本就无法证明满足下限：不默认放行。"""
    monkeypatch.setattr(renderer_node.subprocess, "run", _fake_node_run("not-a-version"))

    with pytest.raises(RuntimeError) as error:
        renderer_node.render_markdown_node("# x", renderer_version="v2")

    assert "无法解析 Node 版本" in str(error.value)


def test_the_default_and_explicit_v1_never_touch_the_v2_bridge(monkeypatch):
    calls = []

    def fake_v1(md_text, context=None):
        calls.append(md_text)
        return {"html": "<p>x</p>", "headings": [], "assets": {}, "warnings": []}

    monkeypatch.setattr(renderer_node, "_render_markdown_v1", fake_v1)
    monkeypatch.setattr(renderer_v2, "render_markdown_v2", _forbidden)
    monkeypatch.setattr(renderer_v2, "validate_v2_runtime", _forbidden)

    assert renderer_node.render_markdown_node("# one")["html"] == "<p>x</p>"
    assert renderer_node.render_markdown_node("# two", renderer_version="v1")["html"] == "<p>x</p>"
    assert calls == ["# one", "# two"]


def test_v1_refuses_renderer_options_and_unknown_versions():
    """v1 的选项是固定的：传 options 或未知版本都必须报错，而不是静默忽略。"""
    with pytest.raises(ValueError) as options_error:
        renderer_node.render_markdown_node("# x", options={"fetch_remote_resources": False})
    assert "v1" in str(options_error.value)

    with pytest.raises(ValueError) as version_error:
        renderer_node.render_markdown_node("# x", renderer_version="v3")
    assert "'v3'" in str(version_error.value)
