"""Markdown 迁移 fixture 语料的测试专用读取层。

语料存在的理由：Markdown 语义的所有权要交给 vscode-office，而这些语法今天只由
demo 快照隐式覆盖。case 登记在 tests/fixtures/markdown/manifest.json 里；manifest
只是索引（schema/id/group/file/note），断言全部写在 Python 测试中，因此本模块不
构造测试 DSL，只负责读取 fixture 并调用真实渲染器。

不参与打包：packaging/MarkdownReader.spec 只收集 gui/assets、templates 与
node_renderer。
"""

import json
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "markdown"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"

ALLOWED_GROUPS = ("keep", "target", "anchor")
CASE_KEYS = ("id", "group", "file", "note")


def load_manifest() -> dict:
    """返回 manifest 的解析结果。"""
    with open(MANIFEST_PATH, "r", encoding="utf-8") as stream:
        return json.load(stream)


def load_cases(group: str) -> list[dict]:
    """按 manifest 顺序返回某一分组登记的全部 case。"""
    if group not in ALLOWED_GROUPS:
        raise ValueError("未登记的 fixture 分组：" + str(group))
    return [case for case in load_manifest()["cases"] if case.get("group") == group]


def fixture_path(case: dict) -> Path:
    """返回一个 case 的 Markdown 文件路径。"""
    return FIXTURE_ROOT / case["file"]


def read_fixture(case: dict) -> str:
    """返回一个 case 的 Markdown 源文本。"""
    return fixture_path(case).read_text(encoding="utf-8")


def render_fixture(case: dict) -> dict:
    """用 production renderer 渲染一个 case 并返回结果。

    source_path 指向 fixture 本身，相对资源按真实文档解析；语料不含跨文档链接，
    因此 document_map 为空。

    这里显式使用 `PRODUCTION_RENDERER_VERSION`，而不是 bridge 自己的默认值：迁移语料
    检验的是 production policy。v2 下同时显式关闭远程抓取，保证语料（含 PlantUML）不会
    访问公共网络 —— PlantUML 因此保留 server URL，其语义仍可断言。
    """
    from core.config import PRODUCTION_RENDERER_VERSION
    from core.renderer_node import render_markdown_node

    path = fixture_path(case)
    options = (
        {"math": True, "fetch_remote_resources": False}
        if PRODUCTION_RENDERER_VERSION == "v2"
        else None
    )
    return render_markdown_node(
        read_fixture(case),
        context={
            "source_path": str(path),
            "output_path": str(path.with_suffix(".html")),
            "document_map": {},
        },
        renderer_version=PRODUCTION_RENDERER_VERSION,
        options=options,
    )
