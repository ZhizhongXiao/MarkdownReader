"""Phase 12A-2: a QA record has to say which release it is evidence for.

The acceptance gate used to read any checklist whose boxes were all ticked and whose
conclusion line was present. That is not enough to freeze a release:
`docs/QA-CHECKLIST.md` is a finished 33/33 record from the v1 renderer era, so the default
invocation could accept v1 evidence for a v2 production release -- measured, not assumed.

The rule locked here has three parts:

* a record declares a canonical identity (``version`` / ``production_renderer`` /
  ``shapes`` / ``platform``) in one ``QA identity`` block;
* the default invocation discovers the record whose identity matches the current release
  instead of trusting a fixed path, and a malformed identity anywhere in the candidate set
  fails closed rather than being skipped;
* an explicit ``--qa-record`` is a deliberate choice, not an exemption: it passes the same
  identity check.

The schema is canonical on purpose. This is a release gate, not a user-facing format, so
there are no aliases and no case-insensitive keys: a misspelling has to fail instead of
being absorbed by compatibility.

Identity here is *record class* identity -- it proves a record belongs to this version and
this production renderer, not that it accepted one exact artifact. Candidate binding (an
archive hash or a source commit) stays open until the build/QA/freeze order of 12A-3 / 12C
is settled, and has to be resolved before the final release.
"""

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# The four canonical keys, in the order a record is expected to state them. The parser
# accepts any order; tests keep one order so failures stay readable.
KEYS = ("version", "production_renderer", "shapes", "platform")


def _load_release_freeze():
    """Import packaging/release_freeze.py by path: `packaging` is also a PyPI name."""
    spec = importlib.util.spec_from_file_location(
        "release_freeze_under_test", ROOT / "packaging" / "release_freeze.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release_freeze = _load_release_freeze()


def capability(name: str):
    """Return a required Phase 12A-2 capability, refusing to guess when it is missing."""
    assert hasattr(release_freeze, name), "release_freeze must expose " + name + " (Phase 12A-2)"
    return getattr(release_freeze, name)


def expected() -> dict:
    """Return the expected identity, refusing to invent fields the gate does not declare."""
    identity = capability("expected_identity")()
    missing = [key for key in KEYS if key not in identity]
    assert not missing, "expected_identity() must declare " + ", ".join(missing)
    return identity


def identity_text(**overrides: str) -> str:
    """Return a canonical identity block, optionally with fields replaced."""
    values = expected()
    values.update(overrides)
    lines = ["QA identity"] + [key + ": " + str(values[key]) for key in KEYS]
    return "\n".join(lines) + "\n"


def historical_text() -> str:
    """Return a record shaped like the v1 era one: finished, but with no identity at all."""
    return (
        "## A. 启动与外壳\n\n"
        "- [X]  启动正常\n"
        "- [X]  没有系统 Node.js 的机器上仍能启动\n\n"
        "- QA 结论：通过\n"
    )


def record_text(
    identity: str | None = None,
    boxes: tuple[str, ...] = ("- [X] 一",),
    conclusion: bool = True,
) -> str:
    """Return a record whose body is complete; the identity block is the variable."""
    parts = ["## QA 身份", "", "```text"]
    if identity is not None:
        parts.append(identity.rstrip("\n"))
    parts += ["```", "", "## 条目", "", *boxes]
    if conclusion:
        parts += ["", "- QA 结论：通过"]
    return "\n".join(parts) + "\n"


def write_record(directory: pathlib.Path, name: str, text: str) -> pathlib.Path:
    """Write a record and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    record = directory / name
    record.write_text(text, encoding="utf-8")
    return record


def refusal_reason(action) -> str:
    """Run `action` and return the reason of the refusal it must raise."""
    error_type = capability("QaRecordError")
    try:
        action()
    except error_type as error:
        return str(getattr(error, "reason", ""))
    raise AssertionError(
        "expected a " + error_type.__name__ + " refusal, but the call returned normally"
    )


def test_the_default_record_is_the_one_whose_identity_matches(tmp_path: pathlib.Path) -> None:
    """A historical record, the current one and a mismatched one: discovery picks the current."""
    docs = tmp_path / "docs"
    write_record(docs, "QA-CHECKLIST-1.0.0-rc1-v1.md", historical_text())
    current = write_record(docs, "QA-CHECKLIST-1.0.0-rc1-v2.md", record_text(identity_text()))
    write_record(docs, "QA-CHECKLIST-next.md", record_text(identity_text(version="9.9.9-rc9")))

    resolve = capability("resolve_qa_record")

    assert resolve(search_dir=docs) == current


def test_the_default_discovery_ignores_records_without_identity(tmp_path: pathlib.Path) -> None:
    """Only a finished v1-era record is present: that is not evidence for this release."""
    docs = tmp_path / "docs"
    write_record(docs, "QA-CHECKLIST-1.0.0-rc1-v1.md", historical_text())

    resolve = capability("resolve_qa_record")

    assert refusal_reason(lambda: resolve(search_dir=docs)) == "no_match"


def test_the_default_discovery_needs_a_full_identity_match(tmp_path: pathlib.Path) -> None:
    """A record that declares an identity, but not this release's, is a non-candidate."""
    docs = tmp_path / "docs"
    write_record(
        docs,
        "QA-CHECKLIST-v1-renderer.md",
        record_text(identity_text(production_renderer="v1")),
    )

    resolve = capability("resolve_qa_record")

    assert refusal_reason(lambda: resolve(search_dir=docs)) == "no_match"


def test_two_matching_records_require_an_explicit_choice(tmp_path: pathlib.Path) -> None:
    """Two records claiming this release: the gate must not pick one silently."""
    docs = tmp_path / "docs"
    write_record(docs, "QA-CHECKLIST-machine-a.md", record_text(identity_text()))
    write_record(docs, "QA-CHECKLIST-machine-b.md", record_text(identity_text()))

    resolve = capability("resolve_qa_record")

    assert refusal_reason(lambda: resolve(search_dir=docs)) == "ambiguous_match"


def test_a_malformed_identity_fails_closed(tmp_path: pathlib.Path) -> None:
    """One good candidate does not license skipping a broken one beside it."""
    docs = tmp_path / "docs"
    write_record(docs, "QA-CHECKLIST-current.md", record_text(identity_text()))
    broken = identity_text() + "\n" + identity_text()
    write_record(docs, "QA-CHECKLIST-broken.md", record_text(broken))

    resolve = capability("resolve_qa_record")

    assert refusal_reason(lambda: resolve(search_dir=docs)) == "identity_malformed"


@pytest.mark.parametrize(
    "label, mutate, reason",
    [
        ("no identity block", lambda: None, "identity_missing"),
        ("wrong version", lambda: identity_text(version="0.9.0-rc1"), "identity_mismatch"),
        ("wrong renderer", lambda: identity_text(production_renderer="v1"), "identity_mismatch"),
        ("one shape only", lambda: identity_text(shapes="onefile"), "identity_mismatch"),
        ("wrong platform", lambda: identity_text(platform="Windows arm64"), "identity_mismatch"),
    ],
)
def test_an_explicit_record_still_has_to_match_the_identity(
    tmp_path: pathlib.Path, label: str, mutate, reason: str
) -> None:
    """Naming a record explicitly chooses a file; it does not waive the identity check."""
    record = write_record(tmp_path / "docs", "QA-CHECKLIST-explicit.md", record_text(mutate()))

    resolve = capability("resolve_qa_record")

    assert refusal_reason(lambda: resolve(explicit=record)) == reason, label


def _without(key: str) -> str:
    return "\n".join(line for line in identity_text().splitlines() if not line.startswith(key))


@pytest.mark.parametrize(
    "label, mutate",
    [
        ("duplicate key", lambda: identity_text() + "version: " + expected()["version"] + "\n"),
        ("unknown key", lambda: identity_text() + "channel: stable\n"),
        ("missing key", lambda: _without("platform") + "\n"),
        ("second identity block", lambda: identity_text() + "\n" + identity_text()),
        ("malformed line", lambda: identity_text().replace("platform:", "platform")),
        (
            "non canonical spelling",
            lambda: identity_text().replace("production_renderer:", "Production_Renderer:"),
        ),
    ],
)
def test_identity_schema_is_canonical_and_fail_closed(
    tmp_path: pathlib.Path, label: str, mutate
) -> None:
    """Misspellings, duplicates and stray lines are release-gate failures, not noise."""
    record = write_record(tmp_path / "docs", "QA-CHECKLIST-schema.md", record_text(mutate()))

    resolve = capability("resolve_qa_record")

    assert refusal_reason(lambda: resolve(explicit=record)) == "identity_malformed", label


def test_a_complete_matching_record_passes_the_gate(tmp_path: pathlib.Path) -> None:
    """The positive control: the stricter gate still accepts a finished, matching record."""
    record = write_record(
        tmp_path / "docs", "QA-CHECKLIST-current.md", record_text(identity_text())
    )

    assert release_freeze.qa_gate(record) is True


def test_an_unfinished_matching_record_is_refused(tmp_path: pathlib.Path) -> None:
    record = write_record(
        tmp_path / "docs",
        "QA-CHECKLIST-current.md",
        record_text(identity_text(), boxes=("- [X] 一", "- [ ] 二")),
    )

    assert release_freeze.qa_gate(record) is False


def test_a_malformed_identity_is_refused_by_the_gate(tmp_path: pathlib.Path) -> None:
    """qa_gate stays a bool gate: a broken identity is simply not acceptable evidence."""
    record = write_record(
        tmp_path / "docs",
        "QA-CHECKLIST-current.md",
        record_text(identity_text() + "version: " + expected()["version"] + "\n"),
    )

    assert release_freeze.qa_gate(record) is False


def test_the_current_record_declares_the_expected_identity() -> None:
    """The record that belongs to the current production renderer must say so."""
    record = ROOT / "docs" / "QA-CHECKLIST-1.0.1-v2.md"
    assert record.is_file(), "the current acceptance record must exist"

    resolve = capability("resolve_qa_record")

    assert resolve(explicit=record) == record


def test_the_historical_v1_record_is_rejected_by_the_current_gate() -> None:
    """33/33 from the v1 era is not evidence for a v2 production release.

    The first assertion is the rule; the second keeps the rejection honest, so nobody can
    satisfy it by writing an identity block into a historical record.
    """
    record = ROOT / "docs" / "QA-CHECKLIST.md"

    assert release_freeze.qa_gate(record) is False, (
        "the gate accepted docs/QA-CHECKLIST.md, a finished record from the v1 renderer era"
    )
    assert "QA identity" not in record.read_text(encoding="utf-8")
