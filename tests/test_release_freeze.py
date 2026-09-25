"""The acceptance gate reads a record a person ticked, so it reads it generously.

docs/QA-CHECKLIST.md is filled in by hand: people write `[X]` instead of `[x]`,
leave a double space after the box, or indent the line. None of that changes what
the box means, so none of it may block a release. What the gate must still refuse
is a record that is unfinished, and one that only claims to be finished.
"""

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_gate():
    """Import packaging/release_freeze.py by path: `packaging` is also a PyPI name."""
    spec = importlib.util.spec_from_file_location(
        "release_freeze_under_test", ROOT / "packaging" / "release_freeze.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release_freeze = _load_gate()
CONCLUSION = "- QA 结论：通过\n"


def _record(tmp_path, body: str) -> pathlib.Path:
    record = tmp_path / "QA-CHECKLIST.md"
    record.write_text(body, encoding="utf-8")
    return record


@pytest.mark.parametrize(
    "shape",
    [
        "- [x] 一",
        "- [X] 一",
        "- [ x ] 一",
        "-  [X]  一",
        "   - [X] 一",
        "- [X]一",
    ],
)
def test_any_tick_shape_counts(tmp_path, shape):
    record = _record(tmp_path, shape + "\n- [X] 二\n" + CONCLUSION)
    assert release_freeze.qa_gate(record) is True


def test_a_mistyped_mark_is_not_a_tick(tmp_path):
    """`[y]` is not a way to say done, and it must not shrink the denominator."""
    record = _record(tmp_path, "- [y] 一\n- [X] 二\n" + CONCLUSION)
    assert release_freeze.qa_gate(record) is False


def test_an_unfinished_record_is_refused(tmp_path):
    record = _record(tmp_path, "- [X] 一\n- [ ] 二\n" + CONCLUSION)
    assert release_freeze.qa_gate(record) is False


def test_a_conclusion_without_ticks_is_refused(tmp_path):
    record = _record(tmp_path, "- [ ] 一\n- [ ] 二\n" + CONCLUSION)
    assert release_freeze.qa_gate(record) is False


def test_a_record_without_boxes_is_refused(tmp_path):
    record = _record(tmp_path, "没有勾选项。\n" + CONCLUSION)
    assert release_freeze.qa_gate(record) is False


def test_a_ticked_record_without_the_conclusion_is_refused(tmp_path):
    record = _record(tmp_path, "- [X] 一\n- [X] 二\n")
    assert release_freeze.qa_gate(record) is False


def test_a_missing_record_is_refused(tmp_path):
    assert release_freeze.qa_gate(tmp_path / "absent.md") is False


def test_the_record_covers_both_renderer_lockfiles():
    """v2 是 production、v1 是 rollback：两套依赖都必须进发布记录。"""
    labels = [label for label, _ in release_freeze.release_inputs()]

    assert any("renderer/package-lock.json" in label and "v2" in label for label in labels)
    assert any("node_renderer/package-lock.json" in label and "v1" in label for label in labels)
    assert "node.exe" in labels


def test_every_release_input_carries_a_real_hash():
    entries = release_freeze.release_inputs()

    assert entries, "a record without build inputs proves nothing"
    for label, value in entries:
        assert len(value) == 64, (label, value)
        assert all(character in "0123456789abcdef" for character in value), (label, value)


def _stub_build(monkeypatch, tmp_path, renderer_ok: bool) -> list:
    """Replace build()'s two seams -- the renderer step and PyInstaller -- with recorders."""
    order: list = []

    def fake_build_renderer() -> bool:
        order.append("renderer")
        return renderer_ok

    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        order.append("pyinstaller:" + str((kwargs.get("env") or {}).get("MR_BUILD_MODE")))
        return FakeResult()

    monkeypatch.setattr(release_freeze, "DIST", tmp_path / "dist")
    monkeypatch.setattr(release_freeze, "build_renderer", fake_build_renderer)
    monkeypatch.setattr(release_freeze, "run", fake_run)
    return order


def test_the_renderer_payload_is_built_once_before_both_packagings(tmp_path, monkeypatch):
    """renderer/dist 是必需载荷：先构建一次，再循环两种形态（不为每个 mode 重建）。"""
    order = _stub_build(monkeypatch, tmp_path, renderer_ok=True)

    assert release_freeze.build() is True
    assert order == ["renderer", "pyinstaller:onefile", "pyinstaller:onedir"]


def test_a_failed_renderer_build_stops_the_release(tmp_path, monkeypatch):
    """载荷构建失败就不能打包：否则打出来的是一个缺 renderer/dist 的残包。"""
    order = _stub_build(monkeypatch, tmp_path, renderer_ok=False)

    assert release_freeze.build() is False
    assert order == ["renderer"], "renderer 步骤失败后不得继续 PyInstaller"
