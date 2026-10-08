"""G4 acceptance: an idle Backend reaps its Node before the host loop exits."""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from backend import service as backend_service  # noqa: E402
from backend.service import Backend  # noqa: E402
from core import config  # noqa: E402


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


def _request(source: Path, output: Path) -> dict[str, object]:
    return {
        "protocol": 1,
        "id": output.stem,
        "method": "convert",
        "params": {
            "input_path": str(source),
            "output_path": str(output),
            "overwrite": True,
            "offline": True,
        },
    }


def test_idle_host_exits_even_when_no_conversion_arrives(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(backend_service, "BACKEND_IDLE_TIMEOUT_SECONDS", 0.3)
    backend = Backend()
    initial_activity = backend._last_activity

    status = backend.handle_request({"protocol": 1, "id": "status", "method": "status"})
    assert status["ok"] is True
    assert backend._last_activity == initial_activity

    assert backend.wait_for_shutdown(timeout=2)
    assert backend._closed is True
    assert backend._renderer.pid is None
    response = backend.handle_request({"protocol": 1, "id": "late", "method": "status"})
    assert response["ok"] is False
    error = response.get("error")
    assert error is not None
    assert error["code"] == "backend_closed"
    backend.close()


def test_conversion_refreshes_idle_deadline_and_expiry_closes_renderer(
    tmp_path: Path,
):
    assert backend_service.BACKEND_IDLE_TIMEOUT_SECONDS == 120
    config_path = _config_file(tmp_path / "config.json")
    source = ROOT / "samples" / "demo.md"
    expected = (ROOT / "samples" / "demo.html").read_bytes()
    backend = Backend(config_path=str(config_path))

    try:
        first_output = tmp_path / "first.html"
        first = backend.handle_request(_request(source, first_output))
        assert first["ok"] is True, first
        assert first_output.read_bytes() == expected
        first_activity = backend._last_activity
        session = backend._renderer._session
        assert session is not None and session._process is not None
        child = session._process
        with backend._condition:
            backend._idle_timeout = 1.0
            backend._condition.notify_all()
        status = backend.handle_request({"protocol": 1, "id": "status", "method": "status"})
        assert status["ok"] is True
        assert backend._last_activity == first_activity

        time.sleep(0.05)
        second_output = tmp_path / "second.html"
        second = backend.handle_request(_request(source, second_output))
        assert second["ok"] is True, second
        assert second_output.read_bytes() == expected
        assert backend._last_activity > first_activity

        assert backend.wait_for_shutdown(timeout=3)
        assert child.poll() == 0
        assert backend._renderer.pid is None
    finally:
        backend.close()


def test_explicit_close_wakes_a_host_waiting_for_shutdown():
    backend = Backend()
    result: list[bool] = []
    waiter = threading.Thread(
        target=lambda: result.append(backend.wait_for_shutdown(timeout=2))
    )
    waiter.start()

    backend.close()
    waiter.join(timeout=2)

    assert not waiter.is_alive()
    assert result == [True]


def test_host_process_returns_only_after_its_renderer_exits(tmp_path: Path):
    config_path = _config_file(tmp_path / "config.json")
    output = tmp_path / "host.html"
    host_code = "\n".join(
        [
            "import json, sys",
            "from backend import service",
            "service.BACKEND_IDLE_TIMEOUT_SECONDS = 0.15",
            "backend = service.Backend(config_path=sys.argv[1])",
            "response = backend.handle_request({",
            "    'protocol': 1, 'id': 'host', 'method': 'convert',",
            "    'params': {'input_path': sys.argv[2], 'output_path': sys.argv[3],",
            "               'overwrite': True, 'offline': True},",
            "})",
            "session = backend._renderer._session",
            "node = session._process if session is not None else None",
            "stopped = backend.wait_for_shutdown(timeout=10)",
            "state = {'convert_ok': response['ok'], 'host_closed': backend._closed,",
            "         'node_pid': node.pid if node is not None else None,",
            "         'node_exit': node.poll() if node is not None else None}",
            "print(json.dumps(state), flush=True)",
            "raise SystemExit(0 if stopped and state['node_exit'] == 0 else 1)",
        ]
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            host_code,
            str(config_path),
            str(ROOT / "samples" / "demo.md"),
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        timeout=30,
        check=True,
    )

    state = json.loads(completed.stdout)
    assert state["convert_ok"] is True
    assert state["host_closed"] is True
    assert isinstance(state["node_pid"], int)
    assert state["node_exit"] == 0
    assert output.read_bytes() == (ROOT / "samples" / "demo.html").read_bytes()
