"""Node runtime ownership: validated once per process, never silently borrowed.

Node and the renderer assets belong to the MarkdownReader runtime rather than to
an individual conversion job. These cases lock that shape: the runtime is probed
once per process, a render reuses the answer, and a packaged build refuses to
borrow a Node from PATH, because that would hide a broken package until it
reaches a machine where Node happens to be missing.
"""

import subprocess

import pytest

from core import renderer_node


@pytest.fixture(autouse=True)
def _fresh_runtime_cache(monkeypatch):
    monkeypatch.setattr(renderer_node, "_RESOLVED_NODE", None)


def _completed(args, stdout):
    return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")


def test_runtime_is_validated_once_per_process(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return _completed(args, "v22.0.0")

    monkeypatch.setattr(renderer_node.subprocess, "run", fake_run)
    first = renderer_node.validate_renderer_runtime()
    second = renderer_node.validate_renderer_runtime()
    assert first == second
    assert len(calls) == 1, "the runtime must be probed once, not once per call"
    assert calls[0][1] == "--version"


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
    assert len(renders) == 2


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
