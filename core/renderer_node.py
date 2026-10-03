"""Node runtime ownership and the v2 renderer bridge."""

import logging
import os
import subprocess
import sys

from core.config import BUNDLE_ROOT

_logger = logging.getLogger(__name__)

_BUNDLED_NODE = os.path.join(BUNDLE_ROOT, "node", "node.exe")
_RESOLVED_NODE: str | None = None
_RESOLVED_NODE_VERSION: str | None = None
_DEFAULT_RENDER_OPTIONS = {"fetch_remote_resources": False}


def _subprocess_window_kwargs() -> dict:
    """Hide Node child process windows on Windows."""
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resolve_node_runtime() -> str:
    """Return the Node executable this run must use.

    A packaged build carries its own Node, so a missing file means the package is
    broken; borrowing a Node from PATH at that point would hide a build error
    until the release reaches a machine without Node installed. A source checkout
    may use the bundled runtime when present and PATH otherwise.
    """
    if os.path.isfile(_BUNDLED_NODE):
        return _BUNDLED_NODE
    if _is_frozen():
        raise RuntimeError(
            f"MarkdownReader 打包物损坏：缺少内置 Node 运行时（{_BUNDLED_NODE}）。"
            "请重新获取完整发布包。"
        )
    return "node"


def probe_node_version(node_command: str) -> str:
    """Return the Node version string, cached once per process."""
    global _RESOLVED_NODE_VERSION
    if _RESOLVED_NODE_VERSION is not None:
        return _RESOLVED_NODE_VERSION

    missing = "未找到可用的 Node.js，请检查内置 Node 或系统 PATH。"
    try:
        result = subprocess.run(
            [node_command, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            **_subprocess_window_kwargs(),
        )
    except FileNotFoundError as error:
        raise RuntimeError(missing) from error
    if result.returncode != 0:
        raise RuntimeError(missing)
    version = (result.stdout or "").strip()
    if not version:
        raise RuntimeError(missing)
    _RESOLVED_NODE_VERSION = version
    return version


def _require_v2_node_major(version: str) -> int:
    """Reject Node versions that cannot run the v2 renderer."""
    from core import renderer_v2

    try:
        major = renderer_v2.node_major(version)
    except ValueError as error:
        raise RuntimeError(
            f"无法解析 Node 版本，renderer v2 需要 major >= "
            f"{renderer_v2.MINIMUM_NODE_MAJOR}：{error}"
        ) from error
    if major < renderer_v2.MINIMUM_NODE_MAJOR:
        raise RuntimeError(
            f"renderer v2 需要 Node major >= {renderer_v2.MINIMUM_NODE_MAJOR}，当前为 {version}。"
            "请升级内置 Node。"
        )
    return major


def validate_renderer_runtime() -> str:
    """Validate Node and the v2 artifact once, then remember the runtime."""
    global _RESOLVED_NODE
    if _RESOLVED_NODE is not None:
        return _RESOLVED_NODE

    node_command = resolve_node_runtime()
    _require_v2_node_major(probe_node_version(node_command))
    from core import renderer_v2

    renderer_v2.validate_v2_runtime(node_command)
    _RESOLVED_NODE = node_command
    _logger.debug("Node 与 v2 渲染运行时已就绪：%s", node_command)
    return node_command


def render_markdown_node(md_text, context=None, *, options=None):
    """Render Markdown with the only supported renderer, v2."""
    from core import renderer_v2

    node_command = validate_renderer_runtime()
    render_options = _DEFAULT_RENDER_OPTIONS if options is None else options
    return renderer_v2.render_markdown_v2(node_command, md_text, context, render_options)
