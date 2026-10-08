"""v2 renderer bridge：调用 renderer/dist/renderer.cjs 并校验它的 envelope。

职责边界（Cutover C2 / K26）—— 只有这一层：

  * `renderer.cjs` 构建产物的存在性检查（缺失即 actionable failure）；
  * v2 运行时冒烟（离线：显式关闭远程抓取，并证明 `dist/katex` 真的可加载）；
  * subprocess 协议（request 走 stdin，stdout 只接受一个 JSON 对象）；
  * envelope 契约（`protocol_version == 2`、`ok`、必在键与形状、renderer 错误码传播）。

**不做**的事：解析 Node 可执行文件、读 Node 版本、判定 Node 下限。那是运行时归属，由
`core/renderer_node.py` 判定一次后把已解析的命令交进来（Node 版本全项目只读一次）。

**导入必须无副作用**：`packaging/MarkdownReader.spec` 在构建期
`from core.renderer_v2 import MINIMUM_NODE_MAJOR`，因此模块加载时只能定义常量与函数 ——
不检查 artifact、不启动 Node、不跑冒烟。真正的验证只发生在函数被显式调用时。同理本模块
**不导入 `core.renderer_node`**（保持自包含，spec 的导入不牵扯运行时模块），代价是同一个
Windows 子进程细节在这里各写一份。
"""

import json
import logging
import os
import subprocess
import time
from collections.abc import Mapping
from typing import Literal, NotRequired, TypedDict, cast

from core.config import BUNDLE_ROOT

_logger = logging.getLogger(__name__)

# v2 renderer 的能力下限：Node 18 起才有稳定的 CJS/ESM 互操作与内置 fetch。
MINIMUM_NODE_MAJOR = 18

# 构建产物（不入库）：源码布局 = <repo>/renderer/dist/renderer.cjs，
# 打包布局 = <bundle>/renderer/dist/。
# 把 renderer/dist/ 收进发布包属于 C4 的 packaging cutover；本模块只保证「缺了就明确失败」。
ARTIFACT = os.path.join(BUNDLE_ROOT, "renderer", "dist", "renderer.cjs")

BUILD_HINT = "请先执行：cd renderer; npm ci; npm run build"

PROTOCOL_VERSION = 2

# 实现策略，不是契约：v2 要覆盖远程抓取（8 s 超时 + 1 次 retry + 并发 4）；远程失败一律
# fail-open，因此不会无限等待。
TIMEOUT_SECONDS = 120

REQUIRED_ENVELOPE_KEYS = ("html", "headings", "features", "warnings", "resources")
REQUIRED_RESOURCE_KEYS = ("items", "styles", "scripts", "author_references")


class RendererFeatures(TypedDict):
    katex: bool
    mermaid: bool
    plantuml: bool
    checkbox: bool
    callout: bool
    wikilink: bool
    mark: bool
    obsidian_tag: bool


class RendererResourceItem(TypedDict):
    kind: str
    source: str
    ref: str
    status: Literal["inlined", "kept", "failed"]
    mime: NotRequired[str]
    resolved: NotRequired[str]


class RendererStyle(TypedDict):
    id: str
    css: str


class RendererScript(TypedDict):
    id: str
    version: str
    script: str
    boot: str


class AuthorReference(TypedDict):
    ref: str
    count: int


class RendererResources(TypedDict):
    items: list[RendererResourceItem]
    styles: list[RendererStyle]
    scripts: list[RendererScript]
    author_references: list[AuthorReference]


class RendererEnvelope(TypedDict):
    """Successful v2 renderer response after the protocol gate."""

    protocol_version: Literal[2]
    ok: Literal[True]
    html: str
    headings: list[dict]
    features: RendererFeatures
    warnings: list[str]
    resources: RendererResources

# 冒烟输入是**显式**写的，不依赖 adapter 当前的默认值：`fetch_remote_resources=False` 让
# 「绝不联网」成为输入保证；`math=True` 与公式样本一起证明 `dist/katex` 真的被加载
# （`options.math` 控制 KaTeX 是否注册，见 renderer/upstream/create_renderer.js）。
SMOKE_MARKDOWN = "# 自检\n\n行内公式 $a^2+b^2=c^2$。\n"
SMOKE_OPTIONS = {"fetch_remote_resources": False, "math": True}

# The first real renderer request carries the offline runtime smoke in the same Node process.
_VALIDATED_RUNTIME: str | None = None


def node_major(version: str) -> int:
    """Return the major number of a Node version string ("v24.20.0" -> 24).

    纯函数：解析失败抛 ValueError，由调用方（core/renderer_node.py 的下限判定）决定
    怎么失败 —— 解析不出来就意味着无法证明满足下限。
    """
    text = str(version or "").strip().lstrip("vV")
    head = text.split(".", 1)[0]
    if not head.isdigit():
        raise ValueError(f"无法解析 Node 版本：{version!r}")
    return int(head)


def _subprocess_window_kwargs() -> dict:
    """Hide the Node child window on Windows (与 core/renderer_node.py 同一平台细节)。"""
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def require_artifact() -> str:
    """Return the v2 artifact path, failing actionably when it was never built."""
    if not os.path.isfile(ARTIFACT):
        raise RuntimeError(
            f"v2 renderer 构建产物缺失：{ARTIFACT}。{BUILD_HINT}"
        )
    return ARTIFACT


def _invoke_artifact(
    node_command: str,
    markdown: str,
    options,
    context,
    *,
    runtime_validation: bool = False,
) -> str:
    """Run one renderer process and return its raw stdout."""
    request = {
        "markdown": markdown,
        "options": {} if options is None else dict(options),
        "context": {} if context is None else dict(context),
    }
    if runtime_validation:
        request["runtime_validation"] = {
            "markdown": SMOKE_MARKDOWN,
            "options": SMOKE_OPTIONS,
            "context": {},
        }
    artifact = require_artifact()
    stage = "runtime_validation+request" if runtime_validation else "request"
    started = time.perf_counter()
    try:
        result = subprocess.run(
            [node_command, artifact],
            input=json.dumps(request, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            cwd=os.path.dirname(artifact),
            **_subprocess_window_kwargs(),
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"v2 renderer 运行超过 {TIMEOUT_SECONDS} 秒，已超时。") from error
    except Exception as error:
        raise RuntimeError(f"运行 v2 renderer 失败：{error}") from error
    finally:
        _logger.debug(
            "timing stage=renderer_process purpose=%s elapsed_ms=%.2f",
            stage,
            (time.perf_counter() - started) * 1000,
        )

    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "(no stderr)"
        raise RuntimeError(
            f"v2 renderer 执行失败（退出码 {result.returncode}）。错误输出：{stderr}"
        )
    return result.stdout or ""


def parse_envelope(stdout: str) -> RendererEnvelope:
    """Validate one v2 envelope and return it unchanged.

    严格按 K26：选了 v2 就必须拿到 v2 —— 不探测协议、不把别的形状猜成成功、不压缩字段。
    返回完整 envelope（`html` / `headings` / `features` / `warnings` / `resources`）：
    C3 的 assembler 需要 `resources`，converter 还需要 `headings`。
    """
    text = (stdout or "").strip()
    if not text:
        raise RuntimeError("v2 renderer 返回了空结果。")
    try:
        output = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"v2 renderer 返回了无效 JSON：{text[:500]}") from error
    if not isinstance(output, dict):
        raise RuntimeError(f"v2 renderer 返回的不是 JSON 对象：{text[:200]}")

    protocol = output.get("protocol_version")
    if protocol != PROTOCOL_VERSION:
        raise RuntimeError(
            f"v2 renderer 返回了非 v2 协议（protocol_version={protocol!r}，"
            f"期望 {PROTOCOL_VERSION}）：不做协议探测。"
        )

    if output.get("ok") is not True:
        error = output.get("error")
        error = error if isinstance(error, dict) else {}
        code = str(error.get("code") or "unknown")
        message = str(error.get("message") or "").strip() or "（renderer 未提供消息）"
        detail = str(error.get("detail") or "").strip()
        suffix = f"（{detail}）" if detail else ""
        raise RuntimeError(f"v2 renderer 失败 [{code}]：{message}{suffix}")

    missing = [key for key in REQUIRED_ENVELOPE_KEYS if key not in output]
    if missing:
        raise RuntimeError(f"v2 renderer 的 envelope 缺少必在字段：{', '.join(missing)}")
    if not isinstance(output["html"], str):
        raise RuntimeError("v2 renderer 的 html 不是字符串。")
    resources = output["resources"]
    if not isinstance(resources, dict):
        raise RuntimeError("v2 renderer 的 resources 不是对象。")
    invalid = [key for key in REQUIRED_RESOURCE_KEYS if not isinstance(resources.get(key), list)]
    if invalid:
        raise RuntimeError(f"v2 renderer 的 resources 缺少列表字段：{', '.join(invalid)}")
    # json.loads() has no schema-aware return type. The protocol gate above validates the
    # success discriminant, required channels, HTML text, and resource channel containers;
    # keep the original object (including additive fields) while assigning the pinned renderer
    # contract to this JSON boundary.
    return cast(RendererEnvelope, output)


def render_markdown_v2(
    node_command: str,
    markdown: str,
    context: Mapping[str, object] | None = None,
    options: Mapping[str, object] | None = None,
) -> RendererEnvelope:
    """Call the v2 artifact once, merging its first-use smoke into the real request."""
    global _VALIDATED_RUNTIME
    validated_runtime = _VALIDATED_RUNTIME
    needs_validation = validated_runtime is None or validated_runtime != node_command
    started = time.perf_counter()
    stdout = _invoke_artifact(
        node_command,
        markdown,
        options,
        context,
        runtime_validation=needs_validation,
    )
    envelope = parse_envelope(stdout)
    if not needs_validation:
        return envelope

    response = json.loads(stdout)
    if not isinstance(response, dict):
        raise RuntimeError("v2 renderer 返回的不是 JSON 对象。")
    runtime_validation = response.pop("runtime_validation", None)
    if not isinstance(runtime_validation, dict):
        raise RuntimeError("首次 v2 renderer 请求未返回 runtime smoke 证据。")
    smoke_envelope = parse_envelope(json.dumps(runtime_validation, ensure_ascii=False))
    _require_smoke_evidence(smoke_envelope)
    envelope = parse_envelope(json.dumps(response, ensure_ascii=False))
    _VALIDATED_RUNTIME = node_command
    _logger.debug(
        "timing stage=renderer_smoke_ready elapsed_ms=%.2f",
        (time.perf_counter() - started) * 1000,
    )
    return envelope


def _require_smoke_evidence(envelope: RendererEnvelope) -> None:
    """The smoke must prove more than "it returned JSON"."""
    if 'class="katex"' not in envelope["html"]:
        raise RuntimeError("v2 renderer 冒烟未产出公式：dist/katex 或 KaTeX 注册有问题。")
    style_ids = {
        str(style.get("id"))
        for style in envelope["resources"]["styles"]
        if isinstance(style, dict)
    }
    if "katex" not in style_ids:
        raise RuntimeError("v2 renderer 冒烟未交付 KaTeX 样式：dist/katex 不可用。")
    if envelope["resources"]["author_references"]:
        raise RuntimeError("v2 renderer 冒烟的 author_references 必须为空。")
    if envelope["warnings"]:
        raise RuntimeError(f"v2 renderer 冒烟产生了 warning：{envelope['warnings']}")
