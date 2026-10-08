"""G6 acceptance: concurrent starters converge on one Backend owner."""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from backend.named_pipe import DEFAULT_PIPE_NAME, request_named_pipe  # noqa: E402
from backend.ownership import BackendOwnership  # noqa: E402
from core import config  # noqa: E402

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Named Mutex and Pipe require Windows")


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


def _names() -> tuple[str, str]:
    suffix = f"{os.getpid()}.{uuid.uuid4().hex}"
    pipe_name = DEFAULT_PIPE_NAME.rsplit("\\", 1)[0] + f"\\g6.{suffix}"
    mutex_name = f"Local\\MarkdownReader.Test.{suffix}"
    return pipe_name, mutex_name


def _wait_for_file(path: Path, process: subprocess.Popen[str], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(f"Owner process exited early. stdout={stdout!r} stderr={stderr!r}")
        time.sleep(0.02)
    raise AssertionError(f"Owner process did not signal startup within {timeout} seconds.")


def _host_code(idle_timeout: float, delay_after_claim: float, ready_path: Path | None) -> str:
    lines = [
        "import sys, time",
        "from backend import service",
        f"service.BACKEND_IDLE_TIMEOUT_SECONDS = {idle_timeout!r}",
        "from backend.__main__ import _serve",
        "from backend.ownership import BackendOwnership",
    ]
    if ready_path is not None:
        lines.extend(
            [
                "from pathlib import Path",
                "owner = BackendOwnership(sys.argv[3])",
                "assert owner.try_acquire()",
                f"Path({str(ready_path)!r}).write_text('claimed', encoding='utf-8')",
                f"time.sleep({delay_after_claim!r})",
                "raise SystemExit(_serve(sys.argv[1], sys.argv[2], owner))",
            ]
        )
    else:
        lines.extend(
            [
                "raise SystemExit(_serve(",
                "    sys.argv[1], sys.argv[2], BackendOwnership(sys.argv[3]),",
                "))",
            ]
        )
    return "\n".join(lines)


def _start_host(
    *,
    config_path: Path,
    pipe_name: str,
    mutex_name: str,
    idle_timeout: float,
    delay_after_claim: float = 0,
    ready_path: Path | None = None,
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            _host_code(idle_timeout, delay_after_claim, ready_path),
            str(config_path),
            pipe_name,
            mutex_name,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_mutex_is_exclusive_and_abandoned_owner_can_be_recovered(tmp_path: Path):
    _, mutex_name = _names()
    ready_path = tmp_path / "mutex-ready"
    release_path = tmp_path / "mutex-release"
    owner_code = "\n".join(
        [
            "import os, sys, time",
            "from pathlib import Path",
            "from backend.ownership import BackendOwnership",
            "owner = BackendOwnership(sys.argv[1])",
            "assert owner.try_acquire()",
            "Path(sys.argv[2]).write_text('claimed', encoding='utf-8')",
            "while not Path(sys.argv[3]).exists(): time.sleep(0.01)",
            "os._exit(0)",
        ]
    )
    process = subprocess.Popen(
        [sys.executable, "-c", owner_code, mutex_name, str(ready_path), str(release_path)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    contender = BackendOwnership(mutex_name)
    try:
        _wait_for_file(ready_path, process, timeout=5)
        assert contender.try_acquire() is False
        release_path.write_text("exit", encoding="utf-8")
        assert process.wait(timeout=5) == 0
        assert contender.try_acquire() is True
        assert contender.was_abandoned is True
    finally:
        if process.poll() is None:
            release_path.write_text("exit", encoding="utf-8")
            process.wait(timeout=5)
        contender.close()


def test_concurrent_serve_starters_share_one_backend_and_renderer(tmp_path: Path):
    config_path = _config_file(tmp_path / "profile" / "config.json")
    pipe_name, mutex_name = _names()
    ready_path = tmp_path / "owner-claimed"
    owner = _start_host(
        config_path=config_path,
        pipe_name=pipe_name,
        mutex_name=mutex_name,
        idle_timeout=8.0,
        delay_after_claim=0.35,
        ready_path=ready_path,
    )
    try:
        _wait_for_file(ready_path, owner, timeout=5)
        competitor = subprocess.run(
            [
                sys.executable,
                "-c",
                _host_code(8.0, 0, None),
                str(config_path),
                pipe_name,
                mutex_name,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        assert competitor.returncode == 0, competitor.stderr
        initial_status = json.loads(competitor.stdout)
        assert initial_status["ok"] is True
        backend_pid = initial_status["result"]["pid"]
        assert isinstance(backend_pid, int)
        assert initial_status["result"]["renderer_pid"] is None

        output = tmp_path / "single owner.html"
        converted = request_named_pipe(
            {
                "protocol": 1,
                "id": "g6-convert",
                "method": "convert",
                "params": {
                    "input_path": str(ROOT / "samples" / "demo.md"),
                    "output_path": str(output),
                    "overwrite": True,
                    "offline": True,
                },
            },
            pipe_name=pipe_name,
        )
        assert converted["ok"] is True
        assert output.read_bytes() == (ROOT / "samples" / "demo.html").read_bytes()

        renderer_status = request_named_pipe(
            {"protocol": 1, "id": "g6-status", "method": "status", "params": {}},
            pipe_name=pipe_name,
        )
        result = renderer_status.get("result")
        assert result is not None
        renderer_pid = result["renderer_pid"]
        assert isinstance(renderer_pid, int)

        repeated = subprocess.run(
            [
                sys.executable,
                "-c",
                _host_code(8.0, 0, None),
                str(config_path),
                pipe_name,
                mutex_name,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        assert repeated.returncode == 0, repeated.stderr
        repeated_status = json.loads(repeated.stdout)
        assert repeated_status["result"]["pid"] == backend_pid
        assert repeated_status["result"]["renderer_pid"] == renderer_pid
    finally:
        try:
            owner.wait(timeout=10)
        except subprocess.TimeoutExpired:
            subprocess.run(
                ["taskkill", "/PID", str(owner.pid), "/T", "/F"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            owner.wait(timeout=5)

    assert owner.returncode == 0, owner.stderr.read() if owner.stderr else ""
