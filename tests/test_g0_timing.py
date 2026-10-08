"""G0 timing logs must remain observational and preserve renderer output."""

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import converter, renderer_v2  # noqa: E402


def test_conversion_timing_logs_do_not_change_written_html(tmp_path: Path, monkeypatch, caplog):
    source = tmp_path / "input.md"
    output = tmp_path / "output.html"
    source.write_text("# baseline\n", encoding="utf-8")
    monkeypatch.setattr(converter, "render_markdown_node", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        converter,
        "assemble_document",
        lambda *_args, **_kwargs: {"html": "<html>baseline</html>", "assembly_warnings": []},
    )

    with caplog.at_level(logging.DEBUG, logger="core.converter"):
        saved = converter.process_single(
            str(source), str(output), {"template": "modern", "overwrite": True}
        )

    assert saved == str(output)
    assert output.read_bytes() == b"<html>baseline</html>"
    timing_stages = {
        "renderer_total",
        "html_assembly",
        "output_write",
        "conversion_pipeline",
    }
    timing_messages = [record.getMessage() for record in caplog.records]
    for stage in timing_stages:
        assert any(f"timing stage={stage} elapsed_ms=" in message for message in timing_messages)


def test_renderer_request_timing_preserves_stdout(monkeypatch, tmp_path: Path, caplog):
    expected_stdout = '{"protocol_version":2,"ok":true}'
    monkeypatch.setattr(
        renderer_v2, "require_artifact", lambda: str(tmp_path / "renderer.cjs")
    )
    monkeypatch.setattr(
        renderer_v2.RendererSession,
        "request",
        lambda *_args, **_kwargs: expected_stdout,
    )

    with caplog.at_level(logging.DEBUG, logger="core.renderer_v2"):
        stdout = renderer_v2._invoke_artifact("node", "# baseline", {}, {})

    assert stdout == expected_stdout
    assert any(
        "timing stage=renderer_request purpose=request elapsed_ms=" in record.getMessage()
        for record in caplog.records
    )
