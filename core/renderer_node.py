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

# Node 版本同样每进程只读一次：v1 用它确认运行时可用，v2 用它判定渲染器下限（K26）。
_RESOLVED_NODE_VERSION: str | None = None


def _subprocess_window_kwargs() -> dict:
    """Hide Node child process windows on Windows."""
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


# A tiny document with math, used to prove the renderer really works.
_SMOKE_MARKDOWN = "# 自检\n\n行内公式 $a^2+b^2=c^2$。\n"


def _run_renderer_smoke(node_command: str) -> None:
    """Render one tiny document, so a broken renderer cannot pass validation.

    Checking that render.js and node_modules exist is not enough: an empty or
    incomplete node_modules satisfies both checks while the first real
    conversion fails.
    """
    payload = {
        "markdown": _SMOKE_MARKDOWN,
        "options": {"html": True, "math": True},
        "context": {},
    }
    try:
        result = subprocess.run(
            [node_command, _RENDER_JS],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            cwd=os.path.dirname(_RENDER_JS),
            **_subprocess_window_kwargs(),
        )
    except Exception as error:
        raise RuntimeError("Node 渲染器自检无法运行：%s" % error)
    if result.returncode != 0:
        raise RuntimeError(
            "Node 渲染器自检失败（退出码 %d）：%s"
            % (result.returncode, (result.stderr or "").strip() or "无错误输出")
        )
    try:
        output = json.loads((result.stdout or "").strip())
    except json.JSONDecodeError:
        raise RuntimeError("Node 渲染器自检返回了无效 JSON。")
    if not isinstance(output, dict) or not output.get("html"):
        raise RuntimeError("Node 渲染器自检未返回 HTML。")


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


def probe_node_version(node_command: str) -> str:
    """Return the Node version string (e.g. "v24.20.0"), cached once per process.

    全项目读 Node 版本只在这里：v1 用它确认运行时可用，v2 用它判定 `MINIMUM_NODE_MAJOR`。
    版本串为空同样判失败 —— 拿不到版本就无法证明满足 v2 的下限。
    """
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
    # 版本探针与 v2 的下限判定共用同一个实现与缓存。
    probe_node_version(node_command)

    if not os.path.isfile(_RENDER_JS):
        raise RuntimeError("未找到 Node 渲染脚本：%s" % _RENDER_JS)
    node_modules = os.path.join(os.path.dirname(_RENDER_JS), "node_modules")
    if not os.path.isdir(node_modules):
        raise RuntimeError("Node 渲染依赖尚未安装，请运行：cd node_renderer && npm install")

    # Prove the renderer works, not merely that its files exist, before the
    # runtime is remembered for the rest of the process.
    _run_renderer_smoke(node_command)

    _RESOLVED_NODE = node_command
    _logger.debug("Node 渲染运行时已就绪：%s", node_command)
    return node_command


def get_node_command() -> str:
    """Return the resolved Node executable, validating the runtime once."""
    return validate_renderer_runtime()


def _require_v2_runtime() -> str:
    """Resolve Node, enforce the v2 floor and validate the v2 artifact, once per process."""
    node_command = resolve_node_runtime()
    _require_v2_node_major(probe_node_version(node_command))
    # 延迟导入：v1 路径不必加载 v2 桥；spec 只导入常量时也不牵扯运行时模块。
    from core import renderer_v2

    renderer_v2.validate_v2_runtime(node_command)
    return node_command


def validate_renderer_runtime_for(renderer_version: str) -> str:
    """Validate whichever renderer the caller is about to use.

    ``"v1"`` keeps its own validation; ``"v2"`` additionally needs the Node
    capability floor and the built artifact. A production consumer calls this with
    ``core.config.PRODUCTION_RENDERER_VERSION`` at startup, so a broken package
    fails at launch instead of in the middle of a batch.
    """
    if renderer_version == "v1":
        return validate_renderer_runtime()
    if renderer_version == "v2":
        return _require_v2_runtime()
    raise ValueError("renderer_version 只能是 'v1' 或 'v2'，收到：%r" % (renderer_version,))


def render_markdown_node(md_text, context=None, *, renderer_version="v1", options=None):
    """Render Markdown with an explicitly selected renderer version.

    v1（默认）→ `node_renderer/render.js`；v2 → `renderer/dist/renderer.cjs`（Cutover C2 / K26）。
    选择是显式的：不做协议探测，v2 失败也不会静默回退到 v1。`options` 只对 v2 生效。
    """
    if renderer_version == "v1":
        if options:
            raise ValueError(
                "renderer_version='v1' 不接受 options：v1 的渲染选项是固定的，"
                "options 只在 renderer_version='v2' 时生效。"
            )
        return _render_markdown_v1(md_text, context)
    if renderer_version == "v2":
        node_command = _require_v2_runtime()
        # 延迟导入：v1 路径不必加载 v2 桥；spec 只导入常量时也不牵扯运行时模块。
        from core import renderer_v2

        return renderer_v2.render_markdown_v2(node_command, md_text, context, options)
    raise ValueError("renderer_version 只能是 'v1' 或 'v2'，收到：%r" % (renderer_version,))


def _require_v2_node_major(version: str) -> int:
    """Enforce the v2 capability floor.

    策略属于运行时归属（本模块），下限常量属于 v2 桥（单一来源，spec 也读它）。
    解析不出来就等于无法证明满足下限，因此同样失败。
    """
    from core import renderer_v2

    try:
        major = renderer_v2.node_major(version)
    except ValueError as error:
        raise RuntimeError(
            "无法解析 Node 版本，v2 需要 major >= %d：%s"
            % (renderer_v2.MINIMUM_NODE_MAJOR, error)
        ) from error
    if major < renderer_v2.MINIMUM_NODE_MAJOR:
        raise RuntimeError(
            "v2 renderer 需要 Node major >= %d，当前为 %s。请升级内置 Node，"
            "或改用 renderer_version='v1'。" % (renderer_v2.MINIMUM_NODE_MAJOR, version)
        )
    return major


def _render_markdown_v1(md_text, context=None):
    """v1 渲染路径（`node_renderer/render.js`）：Cutover C2 只搬运函数体，行为不变。"""
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
