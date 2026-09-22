"""Node.js Markdown renderer bridge.

Calls node_renderer/render.js via subprocess.
Node receives JSON on stdin, returns JSON on stdout.
"""

import json
import logging
import os
import subprocess
import sys

from core.config import BUNDLE_ROOT

_logger = logging.getLogger(__name__)

_RENDER_JS = os.path.join(BUNDLE_ROOT, "node_renderer", "render.js")
_BUNDLED_NODE = os.path.join(BUNDLE_ROOT, "node", "node.exe")

# The runtime is resolved and validated once per process; renders then reuse it.
_RESOLVED_NODE: str | None = None


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
            "MarkdownReader 打包物损坏：缺少内置 Node 运行时（%s）。请重新获取完整发布包。"
            % _BUNDLED_NODE
        )
    return "node"


def validate_renderer_runtime() -> str:
    """Validate Node and the renderer assets once, then remember the answer.

    Node and its dependencies belong to the runtime, not to an individual
    conversion job, so this check runs once per process instead of once per
    document.
    """
    global _RESOLVED_NODE
    if _RESOLVED_NODE is not None:
        return _RESOLVED_NODE

    node_command = resolve_node_runtime()
    missing = "未找到可用的 Node.js，请检查内置 Node 或系统 PATH。"
    try:
        result = subprocess.run(
            [node_command, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            **_subprocess_window_kwargs(),
        )
    except FileNotFoundError:
        raise RuntimeError(missing)
    if result.returncode != 0:
        raise RuntimeError(missing)

    if not os.path.isfile(_RENDER_JS):
        raise RuntimeError("未找到 Node 渲染脚本：%s" % _RENDER_JS)
    node_modules = os.path.join(os.path.dirname(_RENDER_JS), "node_modules")
    if not os.path.isdir(node_modules):
        raise RuntimeError("Node 渲染依赖尚未安装，请运行：cd node_renderer && npm install")

    _RESOLVED_NODE = node_command
    _logger.debug("Node 渲染运行时已就绪：%s", node_command)
    return node_command


def get_node_command() -> str:
    """Return the resolved Node executable, validating the runtime once."""
    return validate_renderer_runtime()


def render_markdown_node(md_text, context=None):
    """Render Markdown text to HTML using Node.js.

    Returns HTML body fragment string.
    """
    # Validated once per process: a render no longer asks whether Node exists.
    node_command = validate_renderer_runtime()

    input_data = {
        "markdown": md_text,
        "options": {"html": True, "math": True},
        "context": context or {},
    }

    try:
        result = subprocess.run(
            [node_command, _RENDER_JS],
            input=json.dumps(input_data, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            cwd=os.path.dirname(_RENDER_JS),
            **_subprocess_window_kwargs(),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Node 渲染器运行超过 30 秒，已超时。")
    except Exception as e:
        raise RuntimeError("运行 Node 渲染器失败：%s" % e)

    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "(no stderr)"
        raise RuntimeError(
            "Node 渲染器执行失败（退出码 %d）。错误输出：%s"
            % (result.returncode, stderr)
        )

    stdout = (result.stdout or "").strip()
    if not stdout:
        raise RuntimeError(
            "Node 渲染器返回了空结果。\n"
            "错误输出：%s" % ((result.stderr or "").strip() or "无")
        )

    try:
        output = json.loads(stdout)
    except json.JSONDecodeError:
        raise RuntimeError("Node 渲染器返回了无效 JSON：%s" % stdout[:500])

    html = output.get("html", "")
    headings = output.get("headings", [])
    warnings = output.get("warnings", [])
    for w in warnings:
        _logger.warning("Node 渲染器：%s", w)

    # Return rendered HTML plus renderer-owned assets. The converter decides
    # where assets belong in the final template.
    return {
        "html": html,
        "headings": headings,
        "assets": output.get("assets", {}),
        "warnings": warnings,
    }
