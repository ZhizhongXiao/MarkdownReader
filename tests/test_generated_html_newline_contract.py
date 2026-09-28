"""Phase 9B2-B: generated HTML is written with LF, on every platform.

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
snapshot compare, and the demo specimen could not be compared byte for byte while the writer
inherited the host newline. These contracts pin the writer, not the comparison.

They run the real entry points (`process_single`, `process_batch`, `build_index`) instead of the
private writer, and each one asserts the negative and the positive together: no CR anywhere in the
file, and real LF line breaks present. A page that is empty, truncated or CRLF-mangled fails.
"""

import sys
from pathlib import Path

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
