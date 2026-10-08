"""Start and call the session Backend through its local Named Pipe."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from typing import Protocol

from backend.named_pipe import DEFAULT_PIPE_NAME, request_named_pipe
from backend.protocol import PROTOCOL_VERSION, Response
from core import paths

_logger = logging.getLogger("gui")
BACKEND_STARTUP_TIMEOUT_SECONDS = 15.0
_STATUS_RETRY_INTERVAL_SECONDS = 0.05


class BackendClientError(RuntimeError):
    """A Backend startup, transport, or structured request failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BackendClientPort(Protocol):
    """Narrow conversion-service surface, also used by isolated tests."""

    def ensure_backend(self) -> Response: ...

    def status(self) -> dict[str, object]: ...

    def request_convert(self, params: Mapping[str, object]) -> dict[str, object]: ...


class BackendProcess(Protocol):
    """The part of a spawned process that startup coordination needs."""

    def poll(self) -> int | None: ...


class BackendClient:
    """Ensure the headless Backend is running, then use its status/convert API."""

    def __init__(
        self,
        *,
        pipe_name: str = DEFAULT_PIPE_NAME,
        startup_timeout: float = BACKEND_STARTUP_TIMEOUT_SECONDS,
        request: Callable[..., Response] = request_named_pipe,
        launcher: Callable[[], BackendProcess] | None = None,
    ) -> None:
        if startup_timeout <= 0:
            raise ValueError("Backend startup timeout must be positive.")
        self.pipe_name = pipe_name
        self._startup_timeout = startup_timeout
        self._request_pipe = request
        self._launcher = launcher or _launch_backend
        self._ensure_lock = threading.Lock()

    def ensure_backend(self) -> Response:
        """Return live status, launching a host only when the pipe has no owner."""
        with self._ensure_lock:
            status = self._try_status()
            if status is not None:
                return status

            try:
                process = self._launcher()
            except OSError as error:
                raise BackendClientError(
                    "backend_start_failed", f"无法启动 MarkdownReader Backend：{error}",
                ) from error

            deadline = time.monotonic() + self._startup_timeout
            while time.monotonic() < deadline:
                status = self._try_status()
                if status is not None:
                    return status
                time.sleep(min(
                    _STATUS_RETRY_INTERVAL_SECONDS,
                    max(0.0, deadline - time.monotonic()),
                ))

            return_code = process.poll()
            detail = f"Backend 进程退出码：{return_code}。" if return_code is not None else ""
            raise BackendClientError(
                "backend_start_timeout",
                f"Backend 未能在 {self._startup_timeout:g} 秒内提供 Named Pipe 服务。{detail}",
            )

    def status(self) -> dict[str, object]:
        """Ensure the host and return its current status result."""
        response = self.ensure_backend()
        result = response.get("result")
        if result is None:
            raise BackendClientError("invalid_backend_response", "Backend status 缺少 result。")
        return result

    def request_convert(self, params: Mapping[str, object]) -> dict[str, object]:
        """Send one convert request after the caller has ensured the host."""
        try:
            response = self._send("convert", params)
        except (OSError, TimeoutError) as error:
            raise BackendClientError("backend_unavailable", f"Backend 连接失败：{error}") from error
        if not response["ok"]:
            detail = response.get("error")
            if detail is None:
                raise BackendClientError(
                    "invalid_backend_response", "Backend 返回了无错误详情的失败响应。",
                )
            raise BackendClientError(detail["code"], detail["message"])
        result = response.get("result")
        if result is None:
            raise BackendClientError("invalid_backend_response", "Backend convert 缺少 result。")
        return result

    def _try_status(self) -> Response | None:
        try:
            response = self._send("status", {})
        except (OSError, TimeoutError):
            return None
        if response["ok"]:
            return response
        detail = response.get("error")
        if detail is not None and detail["code"] == "backend_closed":
            return None
        if detail is None:
            raise BackendClientError(
                "invalid_backend_response", "Backend 返回了无错误详情的失败响应。",
            )
        raise BackendClientError(detail["code"], detail["message"])

    def _send(self, method: str, params: Mapping[str, object]) -> Response:
        request: dict[str, object] = {
            "protocol": PROTOCOL_VERSION,
            "id": uuid.uuid4().hex,
            "method": method,
            "params": dict(params),
        }
        return self._request_pipe(
            request, pipe_name=self.pipe_name, connect_timeout=0.5,
        )


def _launch_backend() -> subprocess.Popen[bytes]:
    """Spawn a GUI-free host; G6 resolves concurrent startup attempts."""
    if paths.is_frozen():
        command = [sys.executable, "--mdr-backend", "serve"]
    else:
        command = [sys.executable, "-m", "backend", "serve"]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        command,
        cwd=paths.application_dir(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    _logger.debug("已启动 Backend host，pid=%s。", process.pid)
    return process
