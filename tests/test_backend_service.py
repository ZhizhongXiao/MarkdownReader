"""G3 acceptance: GUI-free backend host, owned renderer, and v1 request API."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.protocol import Response  # noqa: E402
from backend.service import Backend  # noqa: E402
from core import config, renderer_session, renderer_v2  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_renderer():
    renderer_v2.close_renderer_session()
    yield
    renderer_v2.close_renderer_session()


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


def _request(method: str, params: dict[str, object] | None = None, request_id: str = "g3"):
    return {
        "protocol": 1,
        "id": request_id,
        "method": method,
        "params": {} if params is None else params,
    }


def _result(response: Response) -> dict[str, object]:
    result = response.get("result")
    assert result is not None
    return result


def test_status_is_gui_free_and_does_not_start_node(tmp_path: Path):
    config_path = _config_file(tmp_path / "config.json")
    with Backend(config_path=str(config_path)) as backend:
        response = backend.handle_request(_request("status"))
        assert response["ok"] is True
        result = _result(response)
        repeated_result = _result(backend.handle_request(_request("status")))
        assert result["pid"] == repeated_result["pid"]
        assert result["renderer_pid"] is None
        assert renderer_v2._DEFAULT_BRIDGE.pid is None

    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, sys; from backend.service import Backend; "
            "b = Backend(); r = b.handle_request({'protocol': 1, 'id': 'status', "
            "'method': 'status'}); b.close(); "
            "print(json.dumps({'gui_loaded': any(x == 'gui' or x.startswith('gui.') "
            "for x in sys.modules), 'response': r}))",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=True,
    )
    isolated = json.loads(probe.stdout)
    assert isolated["gui_loaded"] is False
    assert isolated["response"]["result"]["renderer_pid"] is None


def test_backend_conversions_reuse_one_owned_node_and_match_demo_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    original_popen = subprocess.Popen
    children: list[subprocess.Popen[str]] = []
    commands: list[list[str]] = []

    def observe_popen(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        command = args[0] if args else None
        if isinstance(command, (list, tuple)) and any(
            str(part).endswith("renderer.cjs") for part in command
        ):
            commands.append([str(part) for part in command])
            children.append(child)
        return child

    monkeypatch.setattr(renderer_session.subprocess, "Popen", observe_popen)
    config_path = _config_file(tmp_path / "profile" / "config.json")
    source = ROOT / "samples" / "demo.md"
    expected = (ROOT / "samples" / "demo.html").read_bytes()

    with Backend(config_path=str(config_path)) as backend:
        initial = backend.handle_request(_request("status"))
        assert initial["ok"] is True
        assert _result(initial)["renderer_pid"] is None

        pids: list[int] = []
        for index in range(3):
            output = tmp_path / f"demo-{index}.html"
            response = backend.handle_request(
                _request(
                    "convert",
                    {
                        "input_path": str(source),
                        "output_path": str(output),
                        "overwrite": True,
                        "offline": True,
                    },
                    request_id=str(index),
                )
            )
            assert response["ok"] is True, response
            assert _result(response)["output_path"] == str(output)
            assert output.read_bytes() == expected
            status = backend.handle_request(_request("status"))
            assert status["ok"] is True
            renderer_pid = _result(status)["renderer_pid"]
            assert isinstance(renderer_pid, int)
            pids.append(renderer_pid)
            assert renderer_v2._DEFAULT_BRIDGE.pid is None

        assert len(children) == 1
        child = children[0]
        assert commands[0][-1] == "--server"
        assert pids == [child.pid] * 3
        assert child.poll() is None

    assert child.poll() == 0
    assert len(children) == 1


def test_headless_cli_converts_a_single_file(tmp_path: Path):
    output = tmp_path / "cli demo.html"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend",
            "convert",
            str(ROOT / "samples" / "demo.md"),
            "--output",
            str(output),
            "--config",
            str(_config_file(tmp_path / "config.json")),
            "--overwrite",
            "--offline",
        ],
        cwd=ROOT,
        capture_output=True,
        timeout=60,
        check=True,
    )

    response = json.loads(completed.stdout)
    assert response["ok"] is True
    assert response["result"]["output_path"] == str(output)
    assert output.read_bytes() == (ROOT / "samples" / "demo.html").read_bytes()


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"protocol": 2, "id": "x", "method": "status"}, "unsupported_protocol"),
        ({"protocol": 1, "id": "x", "method": "unknown"}, "unknown_method"),
        (
            {"protocol": 1, "id": "x", "method": "status", "params": {"x": 1}},
            "invalid_params",
        ),
        (
            _request("convert", {"input_path": "relative.md"}),
            "invalid_params",
        ),
    ],
)
def test_invalid_requests_return_structured_errors(tmp_path: Path, payload, code: str):
    config_path = _config_file(tmp_path / "config.json")
    with Backend(config_path=str(config_path)) as backend:
        response = backend.handle_request(payload)

    assert response["protocol"] == 1
    assert response["ok"] is False
    error = response.get("error")
    assert error is not None
    assert error["code"] == code


def test_closed_backend_returns_a_structured_error(tmp_path: Path):
    backend = Backend(config_path=str(_config_file(tmp_path / "config.json")))
    backend.close()

    response = backend.handle_request(_request("status"))

    assert response["ok"] is False
    error = response.get("error")
    assert error is not None
    assert error["code"] == "backend_closed"
