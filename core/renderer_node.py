"""Node.js Markdown renderer bridge.

Calls node_renderer/render.js via subprocess.
Node receives JSON on stdin, returns JSON on stdout.
"""

import json
import logging
import os
import subprocess

from core.config import BUNDLE_ROOT

_logger = logging.getLogger(__name__)

_RENDER_JS = os.path.join(BUNDLE_ROOT, "node_renderer", "render.js")
_BUNDLED_NODE = os.path.join(BUNDLE_ROOT, "node", "node.exe")


def _subprocess_window_kwargs() -> dict:
    """Hide Node child process windows on Windows."""
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def get_node_command() -> str:
    """Return bundled Node.js first, then fall back to PATH."""
    if os.path.isfile(_BUNDLED_NODE):
        return _BUNDLED_NODE
    return "node"


def _check_node_available():
    """Raise RuntimeError if Node.js is not available."""
    node_command = get_node_command()
    try:
        result = subprocess.run(
            [node_command, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            **_subprocess_window_kwargs(),
        )
        if result.returncode != 0:
            raise RuntimeError("未找到可用的 Node.js，请检查内置 Node 或系统 PATH。")
    except FileNotFoundError:
        raise RuntimeError("未找到可用的 Node.js，请检查内置 Node 或系统 PATH。")


def _check_renderer_installed():
    """Raise RuntimeError if node_renderer dependencies are not installed."""
    if not os.path.isfile(_RENDER_JS):
        raise RuntimeError("未找到 Node 渲染脚本：%s" % _RENDER_JS)
    node_modules = os.path.join(os.path.dirname(_RENDER_JS), "node_modules")
    if not os.path.isdir(node_modules):
        raise RuntimeError(
            "Node 渲染依赖尚未安装，请运行：cd node_renderer && npm install"
        )


def render_markdown_node(md_text, context=None):
    """Render Markdown text to HTML using Node.js.

    Returns HTML body fragment string.
    """
    _check_node_available()
    _check_renderer_installed()
    node_command = get_node_command()

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
