"""Phase 9B2-B: the HTML writers ask for LF, and the bytes they leave behind are LF.

Two write points produce the pages a reader opens:

* `core.converter._write_output` -- both renderer paths go through it, and
* `core.index_builder.build_index` -- the batch index page.

Both opened the destination in text mode with the platform default newline, so on Windows every
``"\\n"`` in the assembled markup became ``"\\r\\n"``: the same sources produced two different byte
sequences depending on where they were built. The committed specimen `samples/demo.html` is pinned
to LF by `.gitattributes`, so the only reason a fresh Windows render could still be compared against
it was that the contract normalised newlines away -- a tolerance that hides the defect instead of
describing the artifact.

A generated page is a durable artifact: its bytes are what a diff, a checksum or a byte-exact
snapshot compare. That makes two separate facts worth locking, and neither one implies the other:

* **artifact** -- the file that was just written contains no CR and does contain LF. This is what a
  reader and a checksum see, but on Linux and macOS the old implementation wrote LF as well, so on
  its own it cannot tell the fixed writer apart from the broken one.
* **writer intent** -- the call that produced the file asked for ``newline="\\n"``. This is what the
  fix actually establishes, and it is observable on any host (see `TargetWriteRecorder`).

With the byte-exact specimen contract in `test_demo_generation` the three layers read: the artifact
bytes are right here, the writer asks for LF anywhere, and the committed specimen has no other
drift. Every contract runs a real entry point (`process_single`, `process_batch`, `build_index`)
rather than the private writer.
"""

import builtins
import io
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.converter import process_batch, process_single  # noqa: E402
from core.index_builder import DEFAULT_INDEX_FILENAME, build_index  # noqa: E402

# Two paragraphs and a heading: enough line breaks that a CRLF translation is unmistakable, and one
# of them outside the head/tail of the file.
SOURCE_MARKDOWN = "# 标题\n\n第一段正文。\n\n第二段正文。\n"

CONVERSION_SETTINGS = {"template": "modern", "numbering": False, "overwrite": True}


def _write_source(root: Path) -> Path:
    """Write a Markdown source the way the repository keeps its own fixtures: LF only."""
    source = root / "document.md"
    source.write_bytes(SOURCE_MARKDOWN.encode("utf-8"))
    return source


def assert_lf_only(path: Path) -> bytes:
    """Prove a generated page is LF-only and return its bytes.

    Both halves matter: "no CR" would also hold for a file that was never written, and "has LF"
    would also hold for a page that kept a stray CRLF at the end.
    """
    data = path.read_bytes()
    assert data, f"{path.name} was written empty"
    first_cr = data.find(b"\r")
    assert first_cr == -1, (
        f"{path.name} contains a carriage return at byte {first_cr}: a generated page is a durable "
        "artifact and must not inherit the platform default newline. Write it with newline='\\n'."
    )
    assert b"\n" in data, f"{path.name} has no line breaks at all"
    return data


def _comparable(path: object) -> str:
    """Return the path form two spellings of the same file agree on.

    The caller, the configuration and the writer can each spell a path differently, so the recorder
    compares normalised absolute paths rather than raw strings.
    """
    return os.path.normcase(os.path.abspath(str(path)))


def _is_text_write_to(file: object, mode: str, target: str) -> bool:
    """Return True when this ``open()`` call writes text to the file under test.

    Binary writes are excluded deliberately: they take no ``newline``, so counting them would let
    the assertion below fail for a reason that has nothing to do with newline translation.
    """
    if not isinstance(file, (str, bytes, os.PathLike)):
        return False
    if "b" in mode or not any(flag in mode for flag in ("w", "a", "x")):
        return False
    return _comparable(file) == target


class TargetWriteRecorder:
    """Record the keyword arguments the production writers hand to ``open`` for one file.

    Every call is delegated to the real ``open``, so the conversion behaves exactly as it does in
    production: the recorder observes a write, it does not replace it. It is installed on both
    ``builtins.open`` and ``io.open`` (the same function object, so this stays consistent), because
    a writer that switched to ``pathlib.Path.write_text()`` reaches ``io.open`` without touching
    ``builtins``. That keeps the contract about *what the writer asks for*, not about which helper
    it happens to call.
    """

    def __init__(self, target: Path) -> None:
        self._target = _comparable(target)
        self._original = builtins.open
        self.calls: list[dict[str, object]] = []

    def __call__(self, file, mode="r", *args, **kwargs):
        # Delegating without inspecting anything else keeps the wrapped open indistinguishable from
        # the real one, including the errors it raises for a bad mode.
        if _is_text_write_to(file, str(mode), self._target):
            self.calls.append({"mode": str(mode), "newline": kwargs.get("newline")})
        return self._original(file, mode, *args, **kwargs)

    def assert_asked_for_lf(self, page: str) -> None:
        """Prove every text write to `page` requested ``newline="\\n"``."""
        assert self.calls, (
            f"no text write to {page} was observed, so this contract would pass vacuously: the "
            "generated page has to be written through a call this recorder can see. If the writing "
            "strategy changed on purpose -- a temporary file plus os.replace, a copy, a binary "
            "write -- update this contract deliberately instead of leaving it unobservable."
        )
        assert all(call["newline"] == "\n" for call in self.calls), (
            f"every text write to {page} must request newline='\\n' so the writer keeps the LF the "
            "markup already has instead of inheriting the platform default; observed "
            f"{self.calls}."
        )


def observe_target_writes(monkeypatch: pytest.MonkeyPatch, target: Path) -> TargetWriteRecorder:
    """Install a recorder for `target` and return it.

    `monkeypatch` restores both patched names afterwards, including when the contract fails.
    """
    recorder = TargetWriteRecorder(target)
    monkeypatch.setattr(builtins, "open", recorder)
    monkeypatch.setattr(io, "open", recorder)
    return recorder


def test_a_single_conversion_writes_lf_only(tmp_path: Path) -> None:
    """The document from a single conversion carries LF, not the platform newline."""
    source = _write_source(tmp_path)
    output = tmp_path / "out" / "document.html"

    saved = process_single(str(source), str(output), dict(CONVERSION_SETTINGS))

    assert saved is not None, "the conversion must produce a document"
    assert_lf_only(Path(saved))


def test_a_batch_conversion_writes_lf_only_everywhere(tmp_path: Path) -> None:
    """Every HTML file a batch run leaves behind -- documents and index -- carries LF."""
    source = _write_source(tmp_path)
    output_dir = tmp_path / "batch"

    process_batch(
        [str(source)],
        str(output_dir),
        {**CONVERSION_SETTINGS, "build_index": True},
        str(tmp_path),
    )

    pages = sorted(output_dir.rglob("*.html"))
    names = sorted(page.name for page in pages)
    assert len(pages) >= 2, f"the batch run must leave a document and an index behind, saw {names}"
    assert DEFAULT_INDEX_FILENAME in names, f"the batch index is missing, saw {names}"

    for page in pages:
        assert_lf_only(page)


def test_the_index_builder_writes_lf_only(tmp_path: Path) -> None:
    """The index page alone is LF-only, whatever the host default newline is."""
    generated = Path(
        build_index(
            str(tmp_path / "index"),
            [{"filename": "根文档.md", "title": "根文档"}],
            collection_name="契约索引",
        )
    )

    assert generated.name == DEFAULT_INDEX_FILENAME
    assert_lf_only(generated)


def test_the_document_writer_asks_for_lf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The document writer requests LF, so the guarantee does not depend on the host.

    On Linux and macOS the default-newline implementation writes LF too, so the artifact contracts
    above cannot tell it apart from the fixed one. This is the half that can, on any platform.
    """
    source = _write_source(tmp_path)
    output = tmp_path / "out" / "document.html"

    recorder = observe_target_writes(monkeypatch, output)
    saved = process_single(str(source), str(output), dict(CONVERSION_SETTINGS))

    assert saved is not None, "the conversion must produce a document"
    assert Path(saved) == output, "the contract records the write of the document it asked for"
    recorder.assert_asked_for_lf("document.html")


def test_the_index_writer_asks_for_lf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The index writer requests LF for the same reason the document writer does."""
    output_dir = tmp_path / "index"
    target = output_dir / DEFAULT_INDEX_FILENAME

    recorder = observe_target_writes(monkeypatch, target)
    generated = Path(
        build_index(
            str(output_dir),
            [{"filename": "根文档.md", "title": "根文档"}],
            collection_name="契约索引",
        )
    )

    assert generated == target, "the contract records the write of the index it asked for"
    recorder.assert_asked_for_lf(DEFAULT_INDEX_FILENAME)
