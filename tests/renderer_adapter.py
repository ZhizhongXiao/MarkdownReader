"""新 renderer adapter 的测试读取层（Phase 3）。

只负责：定位构建产物、按协议调用它；契约断言留在 test_renderer_adapter_*.py。

产物策略：renderer/dist/renderer.cjs 不入库（优先可重复构建），因此产物缺失是**失败**
并给出构建提示，而不是 skip —— 否则完整测试会在「还没构建」时假绿。只有缺 node 这个
平台工具时才 skip，且只跳过依赖它的检查。

不参与打包：packaging/MarkdownReader.spec 只收集 gui/assets、templates 与 node_renderer。
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RENDERER_DIR = ROOT / "renderer"
ARTIFACT = RENDERER_DIR / "dist" / "renderer.cjs"
UPSTREAM_SUBMODULE = ROOT / "upstream" / "vscode-office"
PIN_MANIFEST = ROOT / "upstream" / "pin.json"

BUILD_HINT = (
    "renderer 构建产物缺失（renderer/dist/renderer.cjs）："
    "请先执行 cd renderer; npm ci; npm run build"
)


def require_node() -> str:
    """返回 node 可执行文件；缺 node 属平台工具缺失，只跳过依赖它的检查。"""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 不在 PATH 上（平台工具缺失）：只跳过新 renderer 的检查。")
    return node


def require_artifact() -> Path:
    """返回构建产物；缺失即失败并给出构建命令。"""
    node = require_node()
    assert node
    if not ARTIFACT.is_file():
        pytest.fail(BUILD_HINT)
    return ARTIFACT


def run_adapter(payload, args: tuple = (), timeout: int = 120) -> subprocess.CompletedProcess:
    """按协议调用 adapter；payload 可以是 dict（自动序列化）或原始字符串。"""
    node = require_node()
    artifact = require_artifact()
    raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return subprocess.run(
        [node, str(artifact), *args],
        input=raw,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(RENDERER_DIR),
    )


def render(markdown: str, options: dict | None = None, context: dict | None = None) -> dict:
    """渲染一段 Markdown 并要求成功，返回 envelope。"""
    completed = run_adapter(
        {"markdown": markdown, "options": options or {}, "context": context or {}}
    )
    assert completed.returncode == 0, completed.stderr
    envelope = json.loads(completed.stdout)
    assert envelope["ok"] is True, envelope
    return envelope
