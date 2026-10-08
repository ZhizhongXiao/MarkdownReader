"""One renderer process and its serialized JSONL transport; no conversion policy."""

import json
import logging
import os
import subprocess
import threading
import time
from collections import deque
from collections.abc import Mapping
from contextlib import suppress
from queue import Empty, Queue

_logger = logging.getLogger(__name__)
SESSION_PROTOCOL = 1
type Exchange = tuple[str, Queue[str | Exception]]


def _exchange_loop(process: subprocess.Popen[str], requests: Queue[Exchange | None]) -> None:
    """Keep blocking writes and reads off the caller so both share its deadline."""
    assert process.stdin is not None and process.stdout is not None
    while (exchange := requests.get()) is not None:
        line, answer = exchange
        try:
            process.stdin.write(line)
            process.stdin.flush()
            response = process.stdout.readline()
            if not response or not response.endswith("\n"):
                raise RuntimeError("renderer Session 在完整响应之前关闭了 stdout。")
            answer.put(response)
        except (OSError, ValueError, RuntimeError) as error:
            answer.put(error)
            return


def _drain_stderr(process: subprocess.Popen[str], tail: deque[str]) -> None:
    assert process.stderr is not None
    try:
        while chunk := process.stderr.read(4096):
            tail.append(chunk)
    except (OSError, ValueError):
        # The process has been closed; stderr is diagnostic, never a response channel.
        return


class RendererSession:
    """Start, exchange, and close one child. A subsequent start replaces a dead child.

    Call start before request. request never silently retries or swaps processes:
    callers can bind their runtime validation to the generation returned by start.
    """

    def __init__(self, node_command: str, artifact: str, *, timeout: float = 120) -> None:
        self.node_command = node_command
        self.artifact = artifact
        self.timeout = timeout
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._requests: Queue[Exchange | None] = Queue()
        self._threads: list[threading.Thread] = []
        self._stderr: deque[str] = deque(maxlen=8)
        self._generation = 0
        self._next_id = 0

    @property
    def pid(self) -> int | None:
        with self._lock:
            process = self._process
            return process.pid if process is not None and process.poll() is None else None

    def start(self) -> int:
        """Lazily start the child; repeated calls return the same generation."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return self._generation
            self._close_locked(force=True)
            started = time.perf_counter()
            try:
                process = subprocess.Popen(
                    [self.node_command, self.artifact, "--server"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    cwd=os.path.dirname(self.artifact),
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except OSError as error:
                raise RuntimeError(f"启动 renderer Session 失败：{error}") from error
            self._process = process
            self._generation += 1
            self._requests = Queue()
            self._stderr = deque(maxlen=8)
            self._threads = [
                threading.Thread(
                    target=_exchange_loop, args=(process, self._requests), daemon=True,
                    name="mdr-renderer-io",
                ),
                threading.Thread(
                    target=_drain_stderr, args=(process, self._stderr), daemon=True,
                    name="mdr-renderer-stderr",
                ),
            ]
            try:
                for thread in self._threads:
                    thread.start()
            except RuntimeError:
                self._close_locked(force=True)
                raise
            _logger.debug(
                "timing stage=node_spawn pid=%s elapsed_ms=%.2f",
                process.pid, (time.perf_counter() - started) * 1000,
            )
            return self._generation

    def request(self, payload: Mapping[str, object]) -> str:
        """Send one frame and return its inner JSON response, with bounded I/O."""
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                self._close_locked(force=True)
                raise RuntimeError("renderer Session 未启动或已退出。")
            self._next_id += 1
            request_id = str(self._next_id)
            line = json.dumps(
                {"protocol": SESSION_PROTOCOL, "id": request_id, "request": dict(payload)},
                ensure_ascii=False,
            ) + "\n"
            answer: Queue[str | Exception] = Queue(maxsize=1)
            self._requests.put((line, answer))
            try:
                response = answer.get(timeout=self.timeout)
                if isinstance(response, Exception):
                    raise RuntimeError(str(response)) from response
                frame = json.loads(response)
                if not isinstance(frame, dict) or frame.get("protocol") != SESSION_PROTOCOL:
                    raise RuntimeError("renderer Session 返回了不支持的传输协议。")
                if frame.get("id") != request_id:
                    raise RuntimeError("renderer Session 响应 ID 与请求不一致。")
                if not isinstance(frame.get("response"), dict):
                    raise RuntimeError("renderer Session 缺少 response 对象。")
                return json.dumps(frame["response"], ensure_ascii=False)
            except (Empty, ValueError, RuntimeError) as error:
                self._close_locked(force=True)
                detail = "".join(self._stderr).strip()
                message = (
                    f"renderer Session 请求超过 {self.timeout} 秒，已超时。"
                    if isinstance(error, Empty) else str(error)
                )
                raise RuntimeError(message + (f"\n{detail}" if detail else "")) from error

    def close(self) -> None:
        """Close stdin, reap the child, and release pipes and reader threads."""
        with self._lock:
            self._close_locked()

    def _close_locked(self, *, force: bool = False) -> None:
        process = self._process
        if process is None:
            return
        self._requests.put(None)
        if force and process.poll() is None:
            process.terminate()
        elif process.stdin is not None:
            with suppress(OSError):
                process.stdin.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                with suppress(OSError):
                    stream.close()
        self._process = None
        self._threads = []
