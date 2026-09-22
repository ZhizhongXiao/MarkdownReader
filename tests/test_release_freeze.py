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
