"""Per-logon Backend ownership and startup-race coordination."""

from __future__ import annotations

import time
import uuid

from backend import named_pipe_win32 as win32
from backend.named_pipe import DEFAULT_PIPE_NAME, request_named_pipe, validate_pipe_name
from backend.protocol import BackendError, Response

DEFAULT_BACKEND_MUTEX_NAME = r"Local\MarkdownReader.Backend.v1"
BACKEND_STARTUP_TIMEOUT_SECONDS = 15.0
_RETRY_INTERVAL_SECONDS = 0.05
_MUTEX_PREFIX = "Local\\"


class BackendOwnership:
    """Own the per-session mutex until this process has stopped its Backend."""

    def __init__(self, mutex_name: str = DEFAULT_BACKEND_MUTEX_NAME) -> None:
        self.mutex_name = _validate_mutex_name(mutex_name)
        self._handle: int | None = None
        self._owned = False
        self.was_abandoned = False

    def try_acquire(self) -> bool:
        """Acquire ownership or report that another server still owns it."""
        if self._owned:
            return True
        if self._handle is None:
            self._handle = win32.create_backend_mutex(self.mutex_name)
        result = win32.wait_mutex(self._handle)
        self._owned = result in {"acquired", "abandoned"}
        self.was_abandoned = result == "abandoned"
        return self._owned

    def close(self) -> None:
        """Release ownership on the acquiring thread and close the mutex handle."""
        if self._handle is None:
            return
        if self._owned:
            win32.release_mutex(self._handle)
            self._owned = False
        win32.close_handle(self._handle)
        self._handle = None


def connect_or_acquire(
    ownership: BackendOwnership,
    *,
    pipe_name: str = DEFAULT_PIPE_NAME,
    startup_timeout: float = BACKEND_STARTUP_TIMEOUT_SECONDS,
) -> Response | None:
    """Return None to the mutex owner, or the live owner's status to a competitor."""
    pipe_name = validate_pipe_name(pipe_name)
    if startup_timeout <= 0:
        raise ValueError("Backend startup timeout must be positive.")
    if ownership.try_acquire():
        return None

    deadline = time.monotonic() + startup_timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            response = request_named_pipe(
                {"protocol": 1, "id": uuid.uuid4().hex, "method": "status", "params": {}},
                pipe_name=pipe_name,
                connect_timeout=min(0.2, remaining),
            )
        except (OSError, TimeoutError) as error:
            last_error = error
        else:
            if response["ok"]:
                return response
            error = response.get("error")
            if error is None or error["code"] != "backend_closed":
                return response

        if ownership.try_acquire():
            return None
        time.sleep(min(_RETRY_INTERVAL_SECONDS, max(0.0, deadline - time.monotonic())))

    message = "现有 Backend 未能在启动等待期限内提供 Named Pipe 服务。"
    if last_error is not None:
        message = f"{message} 最近错误：{last_error}"
    raise BackendError("backend_start_timeout", message)


def _validate_mutex_name(mutex_name: str) -> str:
    if not mutex_name.lower().startswith(_MUTEX_PREFIX.lower()):
        raise ValueError("Backend mutex name must use the Local namespace.")
    suffix = mutex_name[len(_MUTEX_PREFIX):]
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    if not suffix or any(char not in allowed for char in suffix):
        raise ValueError("Backend mutex name must contain one ASCII component.")
    return _MUTEX_PREFIX + suffix
