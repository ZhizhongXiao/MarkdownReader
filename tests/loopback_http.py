"""本地 loopback HTTP 服务器：Phase 5C 网络验收的测试助手。

只监听 127.0.0.1 的临时端口 —— 用来证明**真实 bundled renderer** 的网络路径，同时
不访问公共互联网、不依赖 DNS、不依赖拔网线或随机超时。

路由（路径决定行为，便于直接在 Markdown 里引用）：

    /png/<name>          200 image/png
    /svg/<name>          200 image/svg+xml
    /plain/<name>.png    200 无 Content-Type，路径有图片扩展名 → 扩展名回退
    /plain/<name>        200 无 Content-Type 且无扩展名 → 必须失败
    /html/<name>         200 text/html（错误页，必须拒绝）
    /redirect/<name>     302 → /png/<name>（跟随重定向）
    /status/<code>       HTTP <code>（4xx 不重试、5xx 会重试）
    /slow/<ms>           延迟 <ms> 后 200 PNG（timeout 与并发观测）
    /oversized           200 image/png 且 Content-Length 声明超大 → 必须立即拒绝（不读 body）
    /chunky              200 image/png、无 Content-Length、流式发送大 body → 读取时必须 abort
    /stall/<ms>          200 image/png，先发头与前几字节，停 <ms> 后补完 → **body 读取阶段**超时
    /truncate            200 image/png，声明完整长度却只发前几字节并立即断开 → body 读取阶段网络错误

统计：每个 path 的请求次数 + 并发峰值（in-flight 计数）。
"""

import base64
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)
SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"></svg>'
OVERSIZED_CONTENT_LENGTH = 64 * 1024 * 1024
CHUNK_SIZE = 64 * 1024
CHUNKY_CHUNKS = 8
STALL_HEAD_BYTES = 8
TRUNCATE_DECLARED_LENGTH = 4096
TRUNCATE_SENT_BYTES = 32

PNG_PATH_PREFIX = "/png/"


class LoopbackStats:
    """请求计数与并发峰值；线程安全（ThreadingHTTPServer 会并发处理）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counts: dict[str, int] = {}
        self.in_flight = 0
        self.max_in_flight = 0

    def enter(self, path: str) -> None:
        with self._lock:
            self.counts[path] = self.counts.get(path, 0) + 1
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)

    def leave(self) -> None:
        with self._lock:
            self.in_flight -= 1

    def count(self, path: str) -> int:
        with self._lock:
            return self.counts.get(path, 0)

    def reset(self) -> None:
        with self._lock:
            self.counts = {}
            self.in_flight = 0
            self.max_in_flight = 0


class LoopbackServer:
    """指向 127.0.0.1 临时端口的 URL 构造器 + 统计入口。"""

    def __init__(self, port: int, stats: LoopbackStats) -> None:
        self.port = port
        self.stats = stats

    def url(self, path: str) -> str:
        assert path.startswith("/"), path
        return f"http://127.0.0.1:{self.port}{path}"

    def png(self, name: str = "a.png") -> str:
        return self.url(PNG_PATH_PREFIX + name)


def _handler_factory(stats: LoopbackStats) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:
            """测试输出不需要访问日志。"""
            return

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 的约定名
            path = urlparse(self.path).path
            stats.enter(path)
            try:
                self._route(path)
            finally:
                stats.leave()

        def _write(self, payload: bytes) -> None:
            # 客户端在超限 / 拒绝后可能直接断开，这里静默忽略写失败。
            try:
                self.wfile.write(payload)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

        def _abort(self) -> None:
            """不打招呼直接中断连接：制造「headers 正常、body 读到一半」的网络错误。"""
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.close_connection = True

        def _send(
            self,
            status: int,
            payload: bytes = b"",
            content_type: str | None = None,
            extra_headers: dict[str, str] | None = None,
            declared_length: int | None = None,
            close: bool = True,
        ) -> None:
            self.send_response(status)
            if content_type:
                self.send_header("Content-Type", content_type)
            if declared_length is not None:
                self.send_header("Content-Length", str(declared_length))
            elif close:
                self.send_header("Content-Length", str(len(payload)))
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            if close:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            if payload:
                self._write(payload)

        def _route(self, path: str) -> None:
            if path.startswith("/png/"):
                self._send(200, MINIMAL_PNG, "image/png")
                return
            if path.startswith("/svg/"):
                self._send(200, SVG_BYTES, "image/svg+xml")
                return
            if path.startswith("/plain/"):
                self._send(200, MINIMAL_PNG, None)
                return
            if path.startswith("/html/"):
                self._send(200, b"<html>not an image</html>", "text/html; charset=utf-8")
                return
            if path.startswith("/redirect/"):
                target = PNG_PATH_PREFIX + path.split("/")[-1]
                self._send(302, b"", None, {"Location": target})
                return
            if path.startswith("/status/"):
                self._send(int(path.rsplit("/", 1)[-1]), b"", "text/plain; charset=utf-8")
                return
            if path.startswith("/slow/"):
                time.sleep(int(path.rsplit("/", 1)[-1]) / 1000.0)
                self._send(200, MINIMAL_PNG, "image/png")
                return
            if path == "/oversized":
                self._send(200, b"", "image/png", declared_length=OVERSIZED_CONTENT_LENGTH)
                return
            if path == "/chunky":
                self._send(200, b"", "image/png", close=False)
                for _ in range(CHUNKY_CHUNKS):
                    self._write(b"x" * CHUNK_SIZE)
                self.close_connection = True
                return
            if path.startswith("/stall/"):
                # 头与声明长度都正常，body 停住：客户端只能在读取阶段发现超时。
                self._send(
                    200,
                    b"",
                    "image/png",
                    declared_length=len(MINIMAL_PNG),
                    close=False,
                )
                self._write(MINIMAL_PNG[:STALL_HEAD_BYTES])
                time.sleep(int(path.rsplit("/", 1)[-1]) / 1000.0)
                self._write(MINIMAL_PNG[STALL_HEAD_BYTES:])
                self.close_connection = True
                return
            if path == "/truncate":
                # 声明 4096 B 却只发 32 B 就断开：读取阶段必须是错误，而不是「正常结束」。
                self._send(
                    200,
                    b"",
                    "image/png",
                    declared_length=TRUNCATE_DECLARED_LENGTH,
                    close=False,
                )
                self._write(b"y" * TRUNCATE_SENT_BYTES)
                self._abort()
                return
            self._send(404, b"", "text/plain; charset=utf-8")

    return Handler


@contextmanager
def running_loopback() -> Iterator[LoopbackServer]:
    """启动一个只监听 127.0.0.1 临时端口的服务器；退出时关闭（线程为 daemon）。"""
    stats = LoopbackStats()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_factory(stats))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield LoopbackServer(server.server_address[1], stats)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
