"""Phase 5D 的测试桥：把真实 adapter、assembler 与 closure checker 串起来。

与 `tests/renderer_adapter.py`、`tests/loopback_http.py` 同一约定：这里只负责定位与调用，
契约断言留在 `test_standalone_closure.py` / `test_standalone_matrix.py`。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from renderer_adapter import render  # noqa: E402

from core.html_assembly import assemble_document  # noqa: E402
from tools.standalone_closure import scan  # noqa: E402

DEFAULT_TITLE = "closure fixture"
DEMO_HTML = ROOT / "samples" / "demo.html"


def read_demo_html() -> str:
    """Return the committed production specimen (v1 assembler output)."""
    return DEMO_HTML.read_text(encoding="utf-8")


def assemble(envelope: dict, **kwargs) -> dict:
    """Assemble a v2 envelope with the new assembler (title defaults to a fixture)."""
    kwargs.setdefault("title", DEFAULT_TITLE)
    return assemble_document(envelope, **kwargs)


def assemble_and_scan(
    markdown: str,
    options: dict | None = None,
    context: dict | None = None,
    *,
    allow_network: bool = False,
    author_owned_refs=(),
    **assemble_kwargs,
) -> dict:
    """Render → assemble → scan; returns every intermediate artefact."""
    envelope = render(markdown, options, context, allow_network=allow_network)
    assembled = assemble(envelope, **assemble_kwargs)
    report = scan(
        assembled["html"],
        envelope=envelope,
        injections=assembled["injections"],
        author_owned_refs=author_owned_refs,
    )
    return {"envelope": envelope, "assembled": assembled, "report": report}


def labels(report: dict) -> list[str]:
    """Return the injected labels in document order."""
    return [part["label"] for part in report["payload"]["parts"]]


def payload_bytes(report: dict, label: str) -> int:
    """Return the injected byte size for one label (0 when it was never injected)."""
    return sum(part["bytes"] for part in report["payload"]["parts"] if part["label"] == label)
