"""G5 acceptance: versioned JSONL clients share a local Backend lifecycle."""

import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from backend import named_pipe_win32 as pipe_win32  # noqa: E402
from backend import service as backend_service  # noqa: E402
from backend.named_pipe import (  # noqa: E402
    DEFAULT_PIPE_NAME,
    MAX_FRAME_BYTES,
    NamedPipeServer,
    request_named_pipe,
    validate_pipe_name,
)
from backend.service import Backend  # noqa: E402
from core import config  # noqa: E402

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Named Pipe integration requires Windows")


def _config_file(path: Path) -> Path:
    config.save_config(
        {
            "template": "modern",
            "numbering": False,
            "build_index": False,
            "auto_open": False,
            "external_themes": [],
        },
        str(path),
    )
    return path


def _pipe_name() -> str:
    return DEFAULT_PIPE_NAME.rsplit("\\", 1)[0] + f"\\test.{os.getpid()}.{uuid.uuid4().hex}"


def _request(method: str, request_id: str, params: dict[str, object] | None = None):
    return {
        "protocol": 1,
        "id": request_id,
        "method": method,
        "params": {} if params is None else params,
    }


def _start_server(
    monkeypatch: pytest.MonkeyPatch,
    *,
    idle_timeout: float,
    pipe_name: str,
    config_path: Path | None = None,
) -> tuple[Backend, threading.Thread, list[BaseException]]:
    monkeypatch.setattr(backend_service, "BACKEND_IDLE_TIMEOUT_SECONDS", idle_timeout)
    backend = Backend(config_path=str(config_path) if config_path else None)
    errors: list[BaseException] = []

    def serve() -> None:
        try:
            NamedPipeServer(pipe_name).serve_until_shutdown(backend)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=serve, name="test-named-pipe-host")
    thread.start()
    return backend, thread, errors


def test_pipe_name_requires_local_namespace_and_one_component():
    assert validate_pipe_name(DEFAULT_PIPE_NAME) == DEFAULT_PIPE_NAME
    for name in (
        r"\\server\pipe\MarkdownReader.v1",
        r"\\.\pipe\MarkdownReader.v1",
        DEFAULT_PIPE_NAME + r"\child",
    ):
        with pytest.raises(ValueError):
            validate_pipe_name(name)


def test_concurrent_clients_share_backend_and_convert_demo_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    pipe_name = _pipe_name()
    config_path = _config_file(tmp_path / "config.json")
    backend, thread, errors = _start_server(
        monkeypatch, idle_timeout=8.0, pipe_name=pipe_name, config_path=config_path,
    )
    try:
        first_status = request_named_pipe(_request("status", "first"), pipe_name=pipe_name)
        assert first_status["ok"] is True
        assert first_status["id"] == "first"
        first_result = first_status.get("result")
        assert first_result is not None
        assert first_result["renderer_pid"] is None

        stream_client = pipe_win32.open_client_pipe(pipe_name, timeout=3.0)
        try:
            frames = b"\n".join(
                json.dumps(_request("status", request_id)).encode("utf-8")
                for request_id in ("stream-a", "stream-b")
            ) + b"\n"
            pipe_win32.write_client_pipe(stream_client, frames)
            streamed = [
                json.loads(pipe_win32.read_client_pipe_line(stream_client, MAX_FRAME_BYTES))
                for _ in range(2)
            ]
        finally:
            pipe_win32.close_handle(stream_client)
        assert [response["id"] for response in streamed] == ["stream-a", "stream-b"]

        source = ROOT / "samples" / "demo.md"
        output = tmp_path / "pipe demo.html"
        converted = request_named_pipe(
            _request(
                "convert",
                "convert-1",
                {
                    "input_path": str(source),
                    "output_path": str(output),
                    "overwrite": True,
                    "offline": True,
                },
            ),
            pipe_name=pipe_name,
        )
        assert converted["ok"] is True
        assert output.read_bytes() == (ROOT / "samples" / "demo.html").read_bytes()

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda request_id: request_named_pipe(
                        _request("status", request_id), pipe_name=pipe_name,
                    ),
                    ("parallel-a", "parallel-b"),
                )
            )
        assert [response["id"] for response in responses] == ["parallel-a", "parallel-b"]
        renderer_pids: list[object] = []
        for response in responses:
            result = response.get("result")
            assert result is not None
            renderer_pids.append(result.get("renderer_pid"))
        assert len(set(renderer_pids)) == 1
        assert isinstance(renderer_pids[0], int)
    finally:
        backend.close()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert errors == []


def test_idle_shutdown_cancels_pending_accept_and_idle_client_read(
    monkeypatch: pytest.MonkeyPatch,
):
    pipe_name = _pipe_name()
    backend, thread, errors = _start_server(
        monkeypatch, idle_timeout=0.35, pipe_name=pipe_name,
    )
    client = pipe_win32.open_client_pipe(pipe_name, timeout=3.0)
    try:
        deadline = time.monotonic() + 3
        while thread.is_alive() and time.monotonic() < deadline:
            thread.join(timeout=0.05)
        assert not thread.is_alive(), "pipe host did not stop after Backend shutdown event"
        assert backend._shutdown_event.is_set()
        assert errors == []
    finally:
        pipe_win32.close_handle(client)
        backend.close()
        thread.join(timeout=2)

    with pytest.raises(TimeoutError):
        request_named_pipe(
            _request("status", "after-shutdown"), pipe_name=pipe_name, connect_timeout=0.15,
        )


def test_invalid_json_gets_structured_protocol_error(monkeypatch: pytest.MonkeyPatch):
    pipe_name = _pipe_name()
    backend, thread, errors = _start_server(
        monkeypatch, idle_timeout=3.0, pipe_name=pipe_name,
    )
    client = pipe_win32.open_client_pipe(pipe_name, timeout=3.0)
    try:
        pipe_win32.write_client_pipe(client, b"{invalid}\n")
        response = json.loads(pipe_win32.read_client_pipe_line(client, MAX_FRAME_BYTES))
        assert response["protocol"] == 1
        assert response["id"] is None
        assert response["ok"] is False
        assert response["error"]["code"] == "invalid_json"
    finally:
        pipe_win32.close_handle(client)
        backend.close()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert errors == []
