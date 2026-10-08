"""G7 acceptance: the GUI is a Named Pipe client of the headless Backend."""

import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.named_pipe import DEFAULT_PIPE_NAME, request_named_pipe  # noqa: E402
from backend.protocol import Response  # noqa: E402
from backend.service import Backend  # noqa: E402
from core import config, renderer_v2  # noqa: E402
from gui.api import BridgeApi  # noqa: E402
from gui.services import backend_client as gui_backend_client  # noqa: E402
from gui.services.backend_client import BackendClient  # noqa: E402

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Named Pipe integration requires Windows")


class _Process:
    pid = 1234

    def poll(self) -> int | None:
        return None


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
    return DEFAULT_PIPE_NAME.rsplit("\\", 1)[0] + f"\\g7.{os.getpid()}.{uuid.uuid4().hex}"


def _start_host(
    pipe_name: str,
    config_path: Path,
) -> tuple[Backend, threading.Thread, list[BaseException]]:
    backend = Backend(config_path=str(config_path))
    errors: list[BaseException] = []

    def serve() -> None:
        try:
            from backend.named_pipe import NamedPipeServer

            NamedPipeServer(pipe_name).serve_until_shutdown(backend)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=serve, name="g7-test-backend")
    thread.start()
    return backend, thread, errors


def _wait_for_pipe(pipe_name: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            response = request_named_pipe(
                {"protocol": 1, "id": "g7-ready", "method": "status", "params": {}},
                pipe_name=pipe_name,
                connect_timeout=0.1,
            )
        except (OSError, TimeoutError):
            time.sleep(0.02)
            continue
        assert response["ok"] is True
        return
    raise AssertionError("G7 test Backend did not expose its Named Pipe.")


def test_backend_client_checks_status_then_launches_only_when_missing():
    calls: list[str] = []
    process = _Process()

    def request(
        payload: Mapping[str, object], *, pipe_name: str, connect_timeout: float,
    ) -> Response:
        assert pipe_name.endswith("g7.client")
        assert connect_timeout > 0
        calls.append(str(payload["method"]))
        if len(calls) == 1:
            raise OSError("pipe absent")
        request_id = payload["id"]
        assert isinstance(request_id, str)
        return {
            "protocol": 1,
            "id": request_id,
            "ok": True,
            "result": {"pid": 1234, "renderer_pid": None},
        }

    launches = 0

    def launch() -> _Process:
        nonlocal launches
        launches += 1
        return process

    client = BackendClient(
        pipe_name=DEFAULT_PIPE_NAME.rsplit("\\", 1)[0] + r"\g7.client",
        startup_timeout=1,
        request=request,
        launcher=launch,
    )

    status = client.status()

    assert status["pid"] == 1234
    assert launches == 1
    assert calls == ["status", "status"]


def test_backend_client_uses_existing_host_without_launching():
    def request(
        payload: Mapping[str, object], *, pipe_name: str, connect_timeout: float,
    ) -> Response:
        request_id = payload["id"]
        assert isinstance(request_id, str)
        return {
            "protocol": 1,
            "id": request_id,
            "ok": True,
            "result": {"pid": 2345, "renderer_pid": 9876},
        }

    def forbidden_launch() -> _Process:
        raise AssertionError("an existing Backend must be reused")

    client = BackendClient(request=request, launcher=forbidden_launch)
    assert client.status() == {"pid": 2345, "renderer_pid": 9876}


@pytest.mark.parametrize(
    ("frozen", "expected_tail"),
    [
        (False, ["-m", "backend", "serve"]),
        (True, ["--mdr-backend", "serve"]),
    ],
)
def test_backend_launcher_uses_source_or_frozen_headless_entry(
    monkeypatch: pytest.MonkeyPatch,
    frozen: bool,
    expected_tail: list[str],
):
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_popen(command: list[str], **kwargs: object) -> _Process:
        calls.append((command, kwargs))
        return _Process()

    monkeypatch.setattr(gui_backend_client.paths, "is_frozen", lambda: frozen)
    monkeypatch.setattr(gui_backend_client.paths, "application_dir", lambda: str(ROOT))
    monkeypatch.setattr(gui_backend_client.sys, "executable", "MarkdownReader.exe")
    monkeypatch.setattr(gui_backend_client.subprocess, "Popen", fake_popen)

    gui_backend_client._launch_backend()

    command, options = calls[0]
    expected = ["MarkdownReader.exe", *expected_tail]
    assert command == expected
    assert options["cwd"] == str(ROOT)
    assert options["stdin"] == subprocess.DEVNULL
    assert options["stdout"] == subprocess.DEVNULL
    assert options["stderr"] == subprocess.DEVNULL


def test_bridge_conversion_uses_backend_pipe_and_keeps_demo_bytes(tmp_path: Path):
    renderer_v2.close_renderer_session()
    pipe_name = _pipe_name()
    config_path = _config_file(tmp_path / "profile" / "config.json")
    backend, thread, errors = _start_host(pipe_name, config_path)
    try:
        _wait_for_pipe(pipe_name)
        client = BackendClient(
            pipe_name=pipe_name,
            launcher=lambda: pytest.fail("the ready Backend should be reused"),
        )
        api = BridgeApi(backend_client=client)
        output_dir = tmp_path / "gui-output"
        result = api.convert(
            {
                "inputs": [str(ROOT / "samples" / "demo.md")],
                "output_dir": str(output_dir),
                "overwrite": True,
                "build_index": False,
            }
        )

        assert result["success"] is True, result
        actual_html = Path(result["files"][0]).read_bytes()
        expected_html = (ROOT / "samples" / "demo.html").read_bytes()
        assert actual_html == expected_html
        status = api.get_backend_status()
        assert status["ok"] is True
        backend_status = status.get("result")
        assert isinstance(backend_status, dict)
        assert backend_status["pid"] == os.getpid()
        assert isinstance(backend_status["renderer_pid"], int)
        assert renderer_v2._DEFAULT_BRIDGE.pid is None
    finally:
        backend.close()
        thread.join(timeout=5)
        renderer_v2.close_renderer_session()

    assert not thread.is_alive()
    assert errors == []


def test_gui_batch_preserves_cross_document_links_and_index(tmp_path: Path):
    renderer_v2.close_renderer_session()
    pipe_name = _pipe_name()
    config_path = _config_file(tmp_path / "profile" / "config.json")
    source_root = tmp_path / "batch notes"
    nested = source_root / "nested"
    nested.mkdir(parents=True)
    first = source_root / "first.md"
    second = nested / "second.md"
    first.write_text("[second](nested/second.md)\n", encoding="utf-8")
    second.write_text("# Second\n\nSecond document.\n", encoding="utf-8")
    backend, thread, errors = _start_host(pipe_name, config_path)
    try:
        _wait_for_pipe(pipe_name)
        client = BackendClient(
            pipe_name=pipe_name,
            launcher=lambda: pytest.fail("the ready Backend should be reused"),
        )
        result = BridgeApi(backend_client=client).convert(
            {
                "inputs": [str(source_root)],
                "output_dir": str(tmp_path / "batch-output"),
                "preserve_structure": True,
                "overwrite": True,
                "build_index": True,
            }
        )

        output_root = tmp_path / "batch-output" / "batch notes-HTML"
        assert result["success"] is True, result
        assert len(result["files"]) == 2
        assert 'href="./nested/second.html"' in (output_root / "first.html").read_text(
            encoding="utf-8"
        )
        assert (output_root / "nested" / "second.html").is_file()
        entry_file = result.get("entry_file")
        assert isinstance(entry_file, str)
        assert Path(entry_file).name == "索引-batch notes.html"
        assert Path(entry_file).is_file()
    finally:
        backend.close()
        thread.join(timeout=5)
        renderer_v2.close_renderer_session()

    assert not thread.is_alive()
    assert errors == []


def test_backend_child_dispatch_is_headless_and_gui_has_no_renderer_preflight():
    entrypoint = (ROOT / "main.py").read_text(encoding="utf-8")
    gui_app = (ROOT / "gui" / "app.py").read_text(encoding="utf-8")
    gui_python = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "gui").rglob("*.py")
    )

    assert '"--mdr-backend"' in entrypoint
    assert "from backend.__main__ import main as backend_main" in entrypoint
    assert "validate_renderer_runtime" not in gui_app
    assert "_DEFAULT_BRIDGE" not in gui_python
    assert "core.converter" not in (ROOT / "gui" / "services" / "conversion.py").read_text(
        encoding="utf-8"
    )


def test_importing_gui_does_not_load_backend_renderer_modules():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from gui.api import BridgeApi; "
            "print(sorted(name for name in sys.modules if name in {"
            "'backend.service', 'core.converter', 'core.renderer_v2'}))",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=True,
    )
    assert completed.stdout.strip() == "[]"
