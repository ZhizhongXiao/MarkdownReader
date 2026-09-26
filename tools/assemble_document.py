"""Phase 5D：用真实 adapter + 新 assembler 装配一个页面，供 opt-in 浏览器 smoke 使用。

内置一份集成文档（普通文本 + 行内/展示公式 + Mermaid 图 + 本地图片），因此不需要任何外部
fixture 就能产出「四类载荷同页」的最终 HTML：

    uv run python tools/assemble_document.py --out build/smoke.html
    pwsh tools/run_browser_acceptance.ps1 -ExtraPage build/smoke.html

这里自己调用 dist/renderer.cjs，而不是复用 tests/renderer_adapter.py：tools 不该依赖测试
harness。生产侧的 v2 调用入口会在 production cutover checkpoint 引入，届时这段重复消失。
"""

import argparse
import base64
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import viewer_assets  # noqa: E402
from core.html_assembly import assemble_document  # noqa: E402
from tools.standalone_closure import scan  # noqa: E402

ARTIFACT = ROOT / "renderer" / "dist" / "renderer.cjs"
RENDERER_DIR = ROOT / "renderer"
TITLE = "Phase 5D 集成页"
LOCAL_IMAGE_NAME = "local.png"
MINIMAL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)

DOCUMENT = """# Phase 5D 集成页

普通段落，含行内公式 $a^2+b^2=c^2$ 与展示公式：

$$\\int_0^1 x\\,dx = \\frac{1}{2}$$

```mermaid
graph TD
  A[开始] --> B[结束]
```

![本地图片](local.png)

最后一段普通文本。
"""


def _write_sources(directory: Path) -> Path:
    """Write the built-in document and its local image; return the document path."""
    document = directory / "smoke.md"
    document.write_text(DOCUMENT, encoding="utf-8")
    (directory / LOCAL_IMAGE_NAME).write_bytes(base64.b64decode(MINIMAL_PNG_BASE64))
    return document


def render_envelope(markdown: str, context: dict) -> dict:
    """Render through the built renderer dist with its v2 protocol."""
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("未找到 node：请先安装 Node 18 或更新版本。")
    if not ARTIFACT.is_file():
        raise RuntimeError(
            "缺少 renderer/dist/renderer.cjs：先执行 cd renderer; npm ci; npm run build"
        )
    payload = {"markdown": markdown, "options": {}, "context": context}
    completed = subprocess.run(
        [node, str(ARTIFACT)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(RENDERER_DIR),
        timeout=120,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "renderer 执行失败（exit %d）：%s"
            % (completed.returncode, (completed.stderr or "").strip())
        )
    envelope = json.loads(completed.stdout)
    if not envelope.get("ok"):
        raise RuntimeError("renderer 返回失败：%s" % envelope.get("warnings"))
    return envelope


def build(
    out_path: Path, template_name: str = "modern", external_themes: list[str] | None = None
) -> dict:
    """Render, assemble and scan the built-in smoke document; write `out_path`.

    Paths are resolved first: the renderer runs as a child process whose cwd is
    `renderer/`, so a relative `source_path` would resolve against the wrong
    directory and the local image would silently fail to embed.
    """
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    source_directory = out_path.parent / (out_path.stem + "-sources")
    source_directory.mkdir(parents=True, exist_ok=True)
    document = _write_sources(source_directory)

    context = {
        "source_path": str(document),
        "output_path": str(out_path.parent / (out_path.stem + ".html")),
    }
    envelope = render_envelope(DOCUMENT, context)
    assembled = assemble_document(
        envelope,
        title=TITLE,
        template_name=template_name,
        external_themes=external_themes,
    )
    out_path.write_text(assembled["html"], encoding="utf-8")

    report = scan(assembled["html"], envelope=envelope, injections=assembled["injections"])
    return {"out": str(out_path), "report": report}


def main(argv=None) -> int:
    """Write the smoke page and print its closure verdict; exit 1 on `failure`."""
    parser = argparse.ArgumentParser(
        description="装配 Phase 5D 的浏览器 smoke 页面（真实 adapter + 新 assembler）。"
    )
    parser.add_argument("--out", required=True, help="输出 HTML 路径")
    parser.add_argument("--template", default="modern", help="模板 id（默认 modern）")
    parser.add_argument(
        "--external-theme",
        action="append",
        default=[],
        help="额外携带的外置主题 id（可重复）；用于浏览器验收",
    )
    parser.add_argument(
        "--external-root",
        default="",
        help="外置主题安装目录；给定后覆盖用户资产根（仅测试用）",
    )
    args = parser.parse_args(argv)

    if args.external_root:
        # 只测试用：把「用户主题装在哪」指向临时目录，避免污染仓库自己的用户数据。
        root = str(Path(args.external_root).resolve())
        viewer_assets.external_themes_root = lambda: root

    built = build(
        Path(args.out),
        template_name=args.template,
        external_themes=args.external_theme,
    )
    report = built["report"]
    summary = {
        "out": built["out"],
        "verdict": report["verdict"],
        "total_bytes": report["payload"]["total_bytes"],
        "injected_bytes": report["payload"]["injected_bytes"],
        "resource_payload_bytes": report["payload"]["resource_payload_bytes"],
        "labels": [part["label"] for part in report["payload"]["parts"]],
        "problems": report["problems"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if report["verdict"] == "failure" else 0


if __name__ == "__main__":
    sys.exit(main())
