"""GUI-free service host: configuration, serialized conversions, renderer ownership."""

from __future__ import annotations

import atexit
import logging
import os
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType

from backend.protocol import (
    PROTOCOL_VERSION,
    BackendError,
    ConvertParams,
    Response,
    parse_convert_params,
    parse_request,
)
from core.config import load_config
from core.conversion_plan import is_markdown_path
from core.converter import process_single
from core.renderer_node import validate_renderer_runtime
from core.renderer_v2 import RendererBridge, RendererEnvelope

_logger = logging.getLogger(__name__)
BACKEND_IDLE_TIMEOUT_SECONDS = 120.0


class Backend:
    """One host, one owned bridge, one conversion at a time; construction starts no Node."""

    def __init__(self, *, config_path: str | None = None) -> None:
        started = time.perf_counter()
        self._config_path = os.path.abspath(config_path) if config_path else None
        self._renderer = RendererBridge()
        self._condition = threading.Condition()
        self._shutdown_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        self._closed = False
        self._last_activity = time.monotonic()
        self._idle_timeout = BACKEND_IDLE_TIMEOUT_SECONDS
        self._idle_thread = threading.Thread(
            target=self._expire_when_idle,
            name="mdr-backend-idle",
            daemon=True,
        )
        atexit.register(self.close)
        self._idle_thread.start()
        _logger.debug(
            "timing stage=backend_start elapsed_ms=%.2f", (time.perf_counter() - started) * 1000,
        )

    def __enter__(self) -> Backend:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Refuse new work, wake the host loop, and reap this host's Node."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        self._finish_shutdown()
        self._join_idle_thread()

    def wait_for_shutdown(self, timeout: float | None = None) -> bool:
        """Wait for idle expiry or explicit close; expiry closes Node before returning."""
        stopped = self._shutdown_event.wait(timeout)
        if stopped:
            self._join_idle_thread()
        return stopped

    def _expire_when_idle(self) -> None:
        should_close = False
        with self._condition:
            while not self._closed:
                remaining = self._last_activity + self._idle_timeout - time.monotonic()
                if remaining <= 0:
                    self._closed = True
                    self._condition.notify_all()
                    should_close = True
                    break
                self._condition.wait(timeout=remaining)
        if should_close:
            self._finish_shutdown()

    def _finish_shutdown(self) -> None:
        with self._shutdown_lock:
            if self._shutdown_event.is_set():
                return
            self._renderer.close()
            atexit.unregister(self.close)
            self._shutdown_event.set()

    def _join_idle_thread(self) -> None:
        if threading.current_thread() is not self._idle_thread:
            self._idle_thread.join()

    def handle_request(self, value: object) -> Response:
        """Transport-neutral entry point; every failure is a structured response."""
        request_id = value.get("id") if isinstance(value, dict) else None
        request_id = request_id if isinstance(request_id, str) else None
        try:
            request = parse_request(value)
            with self._condition:
                if self._closed:
                    raise BackendError("backend_closed", "Backend 已关闭。")
                if request.method == "status":
                    result: dict[str, object] = {
                        "pid": os.getpid(), "renderer_pid": self._renderer.pid, "renderer": "v2",
                    }
                else:
                    params = parse_convert_params(request.params)
                    try:
                        result = self._convert(params)
                    finally:
                        self._last_activity = time.monotonic()
                        self._condition.notify_all()
            return {"protocol": PROTOCOL_VERSION, "id": request.id, "ok": True, "result": result}
        except BackendError as error:
            code, message = error.code, str(error)
        except Exception as error:
            _logger.exception("Backend 转换失败")
            code, message = "conversion_failed", str(error)
        return {
            "protocol": PROTOCOL_VERSION, "id": request_id, "ok": False,
            "error": {"code": code, "message": message},
        }

    def _render(
        self, markdown: str, /, context: Mapping[str, object] | None = None,
        *, options: Mapping[str, object] | None = None,
    ) -> RendererEnvelope:
        node = validate_renderer_runtime()
        return self._renderer.render(node, markdown, context, options)

    def _convert(self, params: ConvertParams) -> dict[str, object]:
        source = Path(params.input_path)
        output = Path(params.output_path) if params.output_path else source.with_suffix(".html")
        if not source.is_absolute() or not output.is_absolute():
            raise BackendError("invalid_params", "Backend 输入和输出必须使用绝对路径。")
        if not source.is_file():
            raise BackendError("input_not_found", f"Markdown 文件不存在：{source}")
        if not is_markdown_path(str(source)):
            raise BackendError("invalid_input", "单文件转换只接受 .md 或 .markdown 文件。")
        if output.suffix.lower() not in {".html", ".htm"} or output.is_dir():
            raise BackendError("invalid_output", "输出必须是 .html 或 .htm 文件路径。")
        if output.exists() and source.samefile(output):
            raise BackendError("invalid_output", "输出不能指向 Markdown 源文件。")
        if self._config_path and not os.path.isfile(self._config_path):
            raise BackendError("config_not_found", f"配置文件不存在：{self._config_path}")

        started = time.perf_counter()
        cfg = load_config(self._config_path, runtime_overrides={"overwrite": params.overwrite})
        _logger.debug(
            "timing stage=config_read elapsed_ms=%.2f", (time.perf_counter() - started) * 1000,
        )
        skipped = output.exists() and not cfg.get("overwrite", False)
        report: dict = {}
        started = time.perf_counter()
        try:
            saved = process_single(
                str(source), str(output), cfg, report=report,
                renderer_options={"fetch_remote_resources": False} if params.offline else None,
                renderer=self._render,
            )
        finally:
            _logger.debug(
                "timing stage=backend_convert elapsed_ms=%.2f",
                (time.perf_counter() - started) * 1000,
            )
        if saved is None:
            raise BackendError("conversion_failed", f"生成 HTML 失败：{source}")
        return {"output_path": saved, "warnings": report.get("warnings", []), "skipped": skipped}
