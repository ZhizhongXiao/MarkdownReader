"""The acceptance gate reads a record a person ticked, so it reads it generously.

docs/QA-CHECKLIST.md is filled in by hand: people write `[X]` instead of `[x]`,
leave a double space after the box, or indent the line. None of that changes what
the box means, so none of it may block a release. What the gate must still refuse
is a record that is unfinished, and one that only claims to be finished.
"""

import hashlib
import importlib.util
import pathlib
import sys

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


def _identity_block() -> str:
    """Return the identity the gate now requires, built from the gate's own expectation.

    The fixture grew this block when `qa_gate` started checking identity (Phase 12A-2); every
    tick-shape assertion in this file stays exactly as it was, because what changed is the
    input a record has to satisfy, not how its boxes are counted.
    """
    lines = ["```text", "QA identity"]
    lines += [key + ": " + value for key, value in release_freeze.expected_identity().items()]
    lines += ["```", ""]
    return "\n".join(lines)


def _record(tmp_path, body: str) -> pathlib.Path:
    record = tmp_path / "QA-CHECKLIST.md"
    record.write_text(_identity_block() + "\n" + body, encoding="utf-8")
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


def _bound_candidate(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, str]:
    """Build small exact-hash fixtures for the tag path without invoking a packager."""
    source = "a" * 40
    display = "1.0.1"
    artifact_dir = tmp_path / "candidate" / "dist"
    artifact_dir.mkdir(parents=True)
    exe_name = f"MarkdownReader-{display}-win-x64.exe"
    zip_name = f"MarkdownReader-{display}-portable-win-x64.zip"
    exe = artifact_dir / exe_name
    bundle = artifact_dir / zip_name
    exe.write_bytes(b"onefile artifact")
    bundle.write_bytes(b"portable zip artifact")
    (artifact_dir / "MarkdownReader.exe").write_bytes(b"raw onefile")
    onedir = artifact_dir / "MarkdownReader"
    onedir.mkdir()
    (onedir / "MarkdownReader.exe").write_bytes(b"raw onedir")
    exe_hash = hashlib.sha256(exe.read_bytes()).hexdigest()
    zip_hash = hashlib.sha256(bundle.read_bytes()).hexdigest()
    manifest = artifact_dir.parent / "candidate-manifest-1.0.1.md"
    manifest.write_text(
        "- Source commit: `" + source + "`\n\n"
        "| File | SHA-256 |\n|---|---|\n"
        f"| `{exe_name}` | `{exe_hash}` |\n"
        f"| `{zip_name}` | `{zip_hash}` |\n",
        encoding="utf-8",
    )
    record = tmp_path / "QA-CHECKLIST-1.0.1-v2.md"
    record.write_text(
        f"- Source commit：`{source}`\n"
        f"- Onefile：`{exe_name}`，SHA-256：`{exe_hash}`\n"
        f"- Portable ZIP：`{zip_name}`，SHA-256：`{zip_hash}`\n"
        "- 候选构建记录：`candidate-manifest-1.0.1.md`\n",
        encoding="utf-8",
    )
    return record, artifact_dir, source


def test_candidate_binding_checks_manifest_source_and_both_artifact_hashes(tmp_path, monkeypatch):
    record, artifact_dir, source = _bound_candidate(tmp_path)
    monkeypatch.setattr(release_freeze, "ROOT", tmp_path)

    class GitResult:
        returncode = 0
        stdout = ""

    monkeypatch.setattr(release_freeze, "run", lambda command, **kwargs: GitResult())

    found_source, artifacts = release_freeze.verify_candidate_binding(
        record, artifact_dir, "1.0.1"
    )

    assert found_source == source
    assert [path.name for path in artifacts] == [
        "MarkdownReader-1.0.1-win-x64.exe",
        "MarkdownReader-1.0.1-portable-win-x64.zip",
    ]


def test_candidate_binding_accepts_a_committed_manifest_path(tmp_path, monkeypatch):
    record, artifact_dir, source = _bound_candidate(tmp_path)
    monkeypatch.setattr(release_freeze, "ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "candidate-manifest-1.0.1.md").write_bytes(
        (artifact_dir.parent / "candidate-manifest-1.0.1.md").read_bytes()
    )
    record.write_text(
        record.read_text(encoding="utf-8").replace(
            "`candidate-manifest-1.0.1.md`", "`docs/candidate-manifest-1.0.1.md`"
        ),
        encoding="utf-8",
    )

    class GitResult:
        returncode = 0
        stdout = ""

    monkeypatch.setattr(release_freeze, "run", lambda command, **kwargs: GitResult())

    found_source, _ = release_freeze.verify_candidate_binding(record, artifact_dir, "1.0.1")

    assert found_source == source


def test_candidate_binding_rejects_a_modified_release_artifact(tmp_path, monkeypatch):
    record, artifact_dir, _ = _bound_candidate(tmp_path)
    monkeypatch.setattr(release_freeze, "ROOT", tmp_path)

    class GitResult:
        returncode = 0
        stdout = ""

    monkeypatch.setattr(release_freeze, "run", lambda command, **kwargs: GitResult())
    (artifact_dir / "MarkdownReader-1.0.1-win-x64.exe").write_bytes(b"changed")

    with pytest.raises(release_freeze.CandidateBindingError, match="hash mismatch"):
        release_freeze.verify_candidate_binding(record, artifact_dir, "1.0.1")


def test_candidate_binding_rejects_application_changes_after_build(tmp_path, monkeypatch):
    record, artifact_dir, _ = _bound_candidate(tmp_path)
    monkeypatch.setattr(release_freeze, "ROOT", tmp_path)

    class GitResult:
        returncode = 0
        stdout = ""

    def changed_runtime(command, **kwargs):
        result = GitResult()
        if command[1:3] == ["diff", "--name-only"]:
            result.stdout = "main.py\n"
        return result

    monkeypatch.setattr(release_freeze, "run", changed_runtime)

    with pytest.raises(release_freeze.CandidateBindingError, match="application source changed"):
        release_freeze.verify_candidate_binding(record, artifact_dir, "1.0.1")


def test_tag_path_reuses_bound_candidate_without_rebuilding(tmp_path, monkeypatch):
    record, artifact_dir, source = _bound_candidate(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["release_freeze.py", "--tag", "--artifact-dir", str(artifact_dir)],
    )
    monkeypatch.setattr(release_freeze, "repository_gate", lambda: True)
    monkeypatch.setattr(release_freeze, "resolve_qa_record", lambda explicit=None: record)
    monkeypatch.setattr(release_freeze, "version_agreement", lambda facts: True)
    monkeypatch.setattr(release_freeze, "qa_gate", lambda path: True)
    monkeypatch.setattr(
        release_freeze,
        "verify_candidate_binding",
        lambda path, directory, display: (
            source,
            [directory / "one.exe", directory / "portable.zip"],
        ),
    )
    monkeypatch.setattr(release_freeze, "validate", lambda: True)
    monkeypatch.setattr(release_freeze, "write_record", lambda *args: None)
    monkeypatch.setattr(release_freeze, "create_tag", lambda display: True)
    monkeypatch.setattr(
        release_freeze,
        "build",
        lambda: pytest.fail("tagging must not rebuild the accepted candidate"),
    )

    assert release_freeze.main() == 0
