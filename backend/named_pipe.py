"""Versioned JSONL transport over a per-logon, local-only Windows Named Pipe."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Mapping
from typing import TYPE_CHECKING

from backend import named_pipe_win32 as win32
from backend.protocol import PROTOCOL_VERSION, Response

if TYPE_CHECKING:
    from backend.service import Backend

_logger = logging.getLogger(__name__)
DEFAULT_PIPE_NAME = r"\\.\pipe\LOCAL\MarkdownReader.v1"
_PIPE_PREFIX = "\\\\.\\pipe\\LOCAL\\"
MAX_FRAME_BYTES = 1024 * 1024
_READ_CHUNK_BYTES = 4096


def validate_pipe_name(pipe_name: str) -> str:
    """Accept only one local namespace component, never a remote pipe path."""
    if not pipe_name.lower().startswith(_PIPE_PREFIX.lower()):
        raise ValueError(f"Pipe name must use the local namespace {_PIPE_PREFIX!r}.")
    suffix = pipe_name[len(_PIPE_PREFIX):]
    if not suffix or len(pipe_name) > 240:
        raise ValueError("Pipe name must have a short, non-empty name.")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    if any(char not in allowed for char in suffix):
        raise ValueError("Pipe name contains an unsupported character.")
    return _PIPE_PREFIX + suffix


def request_named_pipe(
    request: Mapping[str, object],
    *,
    pipe_name: str = DEFAULT_PIPE_NAME,
    connect_timeout: float = 5.0,
) -> Response:
    """Send one protocol request and wait for its matching JSONL response."""
    validated_name = validate_pipe_name(pipe_name)
    request_id = request.get("id")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("Named Pipe requests need a non-empty string id.")
    encoded = json.dumps(dict(request), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_FRAME_BYTES:
        raise ValueError("Named Pipe request exceeds the frame limit.")
    handle = win32.open_client_pipe(validated_name, connect_timeout)
    try:
        win32.write_client_pipe(handle, encoded + b"\n")
        line = win32.read_client_pipe_line(handle, MAX_FRAME_BYTES)
    finally:
        win32.close_handle(handle)
    response = _parse_response(line, request_id)
    return response


def _parse_response(line: bytes, expected_id: str) -> Response:
    try:
        value = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OSError("Named Pipe returned invalid JSON.") from error
    if not isinstance(value, dict):
        raise OSError("Named Pipe response must be a JSON object.")
    protocol = value.get("protocol")
    response_id = value.get("id")
    ok = value.get("ok")
    if type(protocol) is not int or protocol != PROTOCOL_VERSION:
        raise OSError("Named Pipe returned an unsupported protocol version.")
    if response_id != expected_id or type(ok) is not bool:
        raise OSError("Named Pipe response id or status does not match the request.")
    if ok:
        result = value.get("result")
        if not isinstance(result, dict) or not all(isinstance(key, str) for key in result):
            raise OSError("Named Pipe success response is missing its result object.")
        return {"protocol": PROTOCOL_VERSION, "id": expected_id, "ok": True, "result": result}
    error = value.get("error")
    if not isinstance(error, dict):
        raise OSError("Named Pipe error response is missing its error object.")
    code, message = error.get("code"), error.get("message")
    if not isinstance(code, str) or not isinstance(message, str):
        raise OSError("Named Pipe error response has invalid details.")
    return {
        "protocol": PROTOCOL_VERSION,
        "id": expected_id,
        "ok": False,
        "error": {"code": code, "message": message},
    }


class NamedPipeServer:
    """Serve independent clients until the Backend's own shutdown event fires."""

    def __init__(self, pipe_name: str = DEFAULT_PIPE_NAME) -> None:
        self.pipe_name = validate_pipe_name(pipe_name)
        self._workers_lock = threading.Lock()
        self._workers: set[threading.Thread] = set()

    def serve_until_shutdown(self, backend: Backend) -> None:
        """Stop accepting and cancel active pipe I/O after Backend shutdown."""
        stop_handle = win32.create_stop_event()
        watcher = threading.Thread(
            target=self._wait_for_backend,
            args=(backend, stop_handle),
            name="mdr-pipe-shutdown",
            daemon=True,
        )
        watcher.start()
        failure: BaseException | None = None
        try:
            _logger.info("Named Pipe host listening on %s", self.pipe_name)
            self._accept_clients(backend, stop_handle)
        except BaseException as error:
            failure = error
        finally:
            win32.signal_event(stop_handle)
            backend.close()
            with self._workers_lock:
                workers = tuple(self._workers)
            for worker in workers:
                worker.join()
            watcher.join()
            win32.close_handle(stop_handle)
        if failure is not None:
            raise failure

    @staticmethod
    def _wait_for_backend(backend: Backend, stop_handle: int) -> None:
        try:
            backend.wait_for_shutdown()
        finally:
            win32.signal_event(stop_handle)

    def _accept_clients(self, backend: Backend, stop_handle: int) -> None:
        while not win32.event_is_set(stop_handle):
            pipe_handle = win32.create_server_pipe(self.pipe_name)
            connected = False
            transferred_to_worker = False
            try:
                connected = win32.connect_server_pipe(pipe_handle, stop_handle)
                if not connected or win32.event_is_set(stop_handle):
                    return
                worker = threading.Thread(
                    target=self._serve_client,
                    args=(backend, pipe_handle, stop_handle),
                    name="mdr-pipe-client",
                    daemon=True,
                )
                with self._workers_lock:
                    if win32.event_is_set(stop_handle):
                        return
                    self._workers.add(worker)
                    try:
                        worker.start()
                    except BaseException:
                        self._workers.discard(worker)
                        raise
                    transferred_to_worker = True
            finally:
                if not transferred_to_worker:
                    if connected:
                        win32.disconnect_server_pipe(pipe_handle)
                    win32.close_handle(pipe_handle)

    def _serve_client(self, backend: Backend, handle: int, stop_handle: int) -> None:
        worker = threading.current_thread()
        try:
            pending = bytearray()
            while not win32.event_is_set(stop_handle):
                chunk = win32.read_server_pipe(handle, _READ_CHUNK_BYTES, stop_handle)
                if chunk is None:
                    return
                pending.extend(chunk)
                while b"\n" in pending:
                    line, _, remainder = pending.partition(b"\n")
                    pending = bytearray(remainder)
                    if not line:
                        continue
                    if len(line) > MAX_FRAME_BYTES:
                        self._write_response(
                            handle,
                            _protocol_error(None, "request_too_large", "请求超过 1 MiB 限制。"),
                            stop_handle,
                        )
                        return
                    response = self._handle_line(backend, bytes(line))
                    if not self._write_response(handle, response, stop_handle):
                        return
                if len(pending) > MAX_FRAME_BYTES:
                    self._write_response(
                        handle, _protocol_error(None, "request_too_large", "请求超过 1 MiB 限制。"),
                        stop_handle,
                    )
                    return
        except OSError as error:
            if not win32.event_is_set(stop_handle):
                _logger.debug("Named Pipe client disconnected: %s", error)
        except Exception:
            _logger.exception("Named Pipe client handling failed")
        finally:
            try:
                win32.disconnect_server_pipe(handle)
            except OSError:
                _logger.debug("Named Pipe disconnect completed with an error", exc_info=True)
            try:
                win32.close_handle(handle)
            finally:
                with self._workers_lock:
                    self._workers.discard(worker)

    @staticmethod
    def _handle_line(backend: Backend, line: bytes) -> Response:
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _protocol_error(None, "invalid_json", "请求必须是有效的 UTF-8 JSON。")
        return backend.handle_request(value)

    @staticmethod
    def _write_response(handle: int, response: Response, stop_handle: int) -> bool:
        encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return win32.write_server_pipe(handle, encoded + b"\n", stop_handle)


def _protocol_error(request_id: str | None, code: str, message: str) -> Response:
    return {
        "protocol": PROTOCOL_VERSION,
        "id": request_id,
        "ok": False,
        "error": {"code": code, "message": message},
    }
