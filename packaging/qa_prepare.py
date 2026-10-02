"""Prepare the material for the current release acceptance run.

Writes a sample document set and an operating guide to a directory **outside** this
repository, because the release freeze refuses to build from a dirty worktree and
the acceptance checklist itself is tracked here.

    python packaging/qa_prepare.py
    python packaging/qa_prepare.py --output "D:/QA" --force
"""

import argparse
import shutil
import struct
import sys
import tomllib
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_VERSION = str(
    tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
)
DISPLAY_VERSION = PROJECT_VERSION.replace("rc", "-rc")
CHECKLIST_PATH = Path("docs") / f"QA-CHECKLIST-{DISPLAY_VERSION}-v2.md"
DEFAULT_OUTPUT = Path.home() / "Documents" / f"MarkdownReader-QA-{DISPLAY_VERSION}"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_png(width: int, height: int) -> bytes:
    """Build a small image without pulling in an imaging library."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw += bytes(((x * 4) % 256, (y * 4) % 256, 128))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (
            struct.pack("!I", len(payload))
            + body
            + struct.pack("!I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    header = struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def build_documents(root: Path) -> None:
    root_doc = """---
title: QA 样例根文档
tags:
  - 公式
  - 图片
  - 脚注
author:
  name: MarkdownReader QA
  links:
    - url: https://example.com
      label: 示例站点
published: true
draft: null
weight: 3
summary: |
  第一行
  第二行
---

# 根文档

这是验收样例的根文档，覆盖 front matter、公式、图片、脚注和跨文档链接。

## 行内公式

质能关系 $E = m c^2$ 与勾股定理 $a^2 + b^2 = c^2$。

## 块级公式

$$
\\int_0^1 x^2 \\, dx = \\frac{1}{3}
$$

## 本地图片

![样例图片](图片/示例.png)

转换后请把生成的 HTML **单独拷到别处**打开：图片仍应显示（已内嵌为 data URI）。

## 表格与代码

| 项目 | 值 |
|---|---|
| A | 1 |
| B | 2 |

```python
def hello(name):
    return "你好，" + name
```

## 脚注

这里引用一个脚注[^1]，以及另一个[^note]。

[^1]: 第一条脚注。
[^note]: 第二条脚注，带**强调**。

## 跨文档链接

- 指向同目录下的 [甲组的一号](甲组/一号.md)
- 指向带空格的 [中文空格目录文档](<中文 空格 目录/文档 一.md>)

## 裸文件名与真链接

正文里的文件名应保持文本：根文档.md、README.md、report.md、版本 1.2.3。
真网址仍应可点：https://example.com 。
"""
    write(root / "根文档.md", root_doc)
    (root / "图片").mkdir(parents=True, exist_ok=True)
    (root / "图片" / "示例.png").write_bytes(make_png(96, 64))

    write(
        root / "甲组" / "一号.md",
        """# 一号文档

回链到 [根文档](../根文档.md)，并指向 [二号文档](二号.md)。

## 小节

用于验证跨文档链接在上面的文档转换后指向生成的 HTML。
""",
    )

    sections = [
        f"## 第 {index} 节\n\n正文内容，用于滚动、折叠和打印分页测试。\n" for index in range(1, 25)
    ]
    write(root / "甲组" / "二号.md", "# 长文文档\n\n" + "\n".join(sections))

    write(
        root / "乙组" / "YAML 全类型.md",
        """---
title: "带引号的标题"
list:
  - 甲
  - 乙
nested:
  name: 嵌套
  items:
    - one
    - two
flag: true
disabled: false
count: 42
ratio: 1.5
nothing: null
block: |
  第一行
  第二行
folded: >
  折行一
  折行二
---

# YAML 全类型

front matter 的嵌套、列表、布尔、数字、null 与多行标量都应被正确解析（页面标题取 title）。
""",
    )

    write(
        root / "中文 空格 目录" / "文档 一.md",
        "# 中文与空格的路径\n\n用于验证中文和空格目录下的转换与索引链接。\n",
    )
    print("documents written under " + str(root))


def build_themes(root: Path) -> None:
    """Copy the two in-repo theme specimens into the acceptance material.

    `samples/qa-themes/` is the source of truth, and this copy is what the reviewer imports.
    Copying the whole directory (not just the CSS) is the point: `metadata.json` declares
    `decorations.css`, and its `url()` needs the local PNG beside it, so a material that lost
    either file would fail the run for the wrong reason (Phase 12 GUI closeout).
    """
    for name in ("qa-ornamented", "qa-no-preview"):
        shutil.copytree(ROOT / "samples" / "qa-themes" / name, root / "主题标本" / name)


GUIDE = """# MarkdownReader __VERSION__ 实机验收操作指引

被测产物（先确认存在）：

    __DIST_DIR__/MarkdownReader-__VERSION__-win-x64.exe
    __DIST_DIR__/MarkdownReader-__VERSION__-portable-win-x64.zip

两种形态都要跑：onefile 用那个 EXE；onedir 解压 ZIP 后运行其中的 MarkdownReader.exe。
目标机不应安装 Python 或 Node/npm（否则先换干净机器，或把 Node 临时移出 PATH）。
需要 Microsoft Edge WebView2 Runtime（系统前置，不随包提供）。

在 GUI 里把「本目录」整体作为输入，输出目录另选一个空目录。
内置主题不需要在转换时选择：每份产物固定携带 Modern / Office / VS Code，阅读时在页面上切换。
观感基线：正文为左对齐；超长链接与裸文件名会在容器内折行，不会被裁掉；
打印输出为白纸加跟随正文的主题块与左右两条框线。
下面每一条按同一顺序对应 `__CHECKLIST_PATH__` 中的条目。

阶段划分：本指引服务的是 **candidate 构建之后的正式 release QA**。GUI closeout 的人工验收是另一次、
在 **source 模式**下进行的检查（记录见 `docs/REFACTOR_ROADMAP.md` 的 Phase 12 GUI closeout 段）：
它不勾本清单、也不写「QA 结论：通过」。正式 checklist 只对**从 GUI seal commit 重新完整构建出来的
exact artifacts** 负责 —— 旧 `dist/`（缺 `themes/template/decorations.css`）已 obsolete，
不作为本次被测产物。

## A 启动与 Windows 集成

- A1 onefile：双击 EXE → 启动图出现后 GUI 正常显示。
- A2 onedir：解压便携 ZIP，运行目录里的 `MarkdownReader.exe` → 同样正常显示。
- A3 目标机没有 Python、也没有 Node/npm；若本机装了系统 Node，先临时把它移出 PATH，
  应用仍能启动并完成一次转换（只使用内置 Node）。
- A4 WebView2：确认目标机已安装 Microsoft Edge WebView2 Runtime；若缺失，应用应给出可读失败，
  而不是空白窗口或静默退出。
- A5 以普通用户（非管理员）身份启动并完成一次转换。
- A6 中文与含空格路径：程序所在目录与输出目录各验证一次。
- A7 onedir：把解压目录里的 `_internal/renderer/dist/renderer.cjs` 临时改名 →
  应用启动即失败并给出可读提示 → 改回后恢复正常（onefile 不做 `_MEIxxxx` 篡改，理由见验收清单）。
## B 打包 smoke

- B1 用「添加文件」原生窗口选 `根文档.md`，按住 Ctrl / Shift 多选
  `甲组/一号.md` 与 `乙组/YAML 全类型.md`。
- B2 分别拖入文件与拖入目录：把 `根文档.md` 拖入窗口；再把「甲组」目录拖入窗口。
- B3 只保留 `根文档.md` 做单文件转换；生成的 HTML 用 Edge 打开，正文、KaTeX 公式、
  本地图片（data URI）都正常。它引用但未入清单的 `甲组/一号.md` 在日志里应给出可读路径
  （不是 `%E7%94%B2…` 这类编码）。
- B4 整个本目录做批量转换（含子目录）：勾选「保留目录结构」时产物落在
  「输出目录/源目录名-HTML/」下，不勾选时全部平铺在输出根目录（同名文件在预检阶段被拦下）。
- B5 批量后打开生成的索引页：列出全部文档，搜索「一号」命中、搜索不存在的词显示无结果，
  复制文件夹绝对路径可粘贴核对。
- B6 含 Mermaid 的文档：断开网络后刷新页面，图形仍能渲染。
- B7 阅读端主题：用 `根文档.md` 生成一次 HTML，在 Edge 里用页面主题切换在
  Modern / Office / VS Code 之间切换 → 立即生效；刷新后仍停在上次选择（阅读偏好存在
  HTML 自己的 localStorage）。转换时无需选主题：三套内置主题永远随产物。
## C 存储与生命周期

- C1 改一次输出目录（或完成一次转换）后，本形态的用户数据根出现 `profile/config.json`；
  单纯启动不创建它；关闭重启后设置恢复。onefile 是
  `%LOCALAPPDATA%/MarkdownReader/profile/config.json`，
  onedir 是 `<应用目录>/data/profile/config.json`。
- C2 设置页「存储信息」：主要信息里的用户数据根与本形态相符（onefile 指向
  `%LOCALAPPDATA%/MarkdownReader/…`，onedir 指向 `<应用目录>/data/…`）；**展开「详细路径」**后
  config / 外置主题目录 / runtime 三条路径同样正确。
- C3 日志与 WebView2 数据只出现在 `<用户数据根>/runtime/` 下；EXE 旁边不应出现 `config.json` 或
  `MarkdownReader.log`。
- C4 onefile：把 EXE 改名或移到另一个目录（含中文与空格）后启动 → 设置、外置主题、日志历史都还在。
- C5 onedir：用户数据只在 `<应用目录>/data/`；把整个应用目录复制到别处运行 → 设置仍在。
- C6 onedir：删除整个应用目录 → 用户数据完全消失（`%LOCALAPPDATA%` 等处没有残留）。

## D 外置主题

- D1 从**本次素材目录**导入两个验收标本（`samples/qa-themes/` 的副本，用来证明素材自带资源）：
  设置页「导入主题…」→ 选 `<素材目录>/主题标本/qa-ornamented` → installed 清单出现该项；
  再导入 `<素材目录>/主题标本/qa-no-preview` → 清单出现第二项。
  回主页：点 `qa-ornamented` 的行体 → 右侧预览舞台换成该主题配色；点 `qa-no-preview` →
  预览舞台隐藏整张示意图，只显示「该主题未提供静态预览」文字；文字水平、垂直居中，文本框填满默认预览区域，但主题仍然可以勾选。
- D2 预览与携带互不干扰：点行体只改变预览；勾复选框只改变携带集合（「已选 N」随之变化），
  且预览保持不动。预览不写任何配置：`profile/config.json` 里不会出现预览字段。
- D3 用 `qa-ornamented` 转换 `根文档.md`（勾选它）→ 生成的 HTML 带
  `theme-qa-ornamented`，正文样式随之改变，装饰资源已内嵌（HTML 里出现
  `data:image/png;base64,`；把 HTML 单独拷到别处打开，装饰仍在）。
- D4 重启应用 → 两个主题仍在 installed 清单里、仍可勾选；文件位于
  `<用户数据根>/assets/themes/external/<id>/`。
- D5 设置页卸载 `qa-ornamented` → 安装副本消失；主页上该 id 变成 missing（并出现主页「移除」）；
  已生成的 HTML 不受影响（资源早已内嵌）。
- D6 设置页点「导出主题模板」→ 选一个空目录（例如 `D:/QA/themes`）→ 该目录下生成
  `markdownreader-theme-template/`。把它复制成 `qa-theme/`，然后**同时**改两处：
  ① `metadata.json`：`id` 从 `my-theme` 改成 `qa-theme`；
  ② 该目录里的每个 CSS 文件：把 `data-theme-id="my-theme"` 改成 `data-theme-id="qa-theme"`，
     把 `theme-my-theme` 改成 `theme-qa-theme`（全文替换即可）。
  只改 `metadata.json` 会被 scope 校验拒绝：外置主题的每条样式规则都必须 scoped 到
  `html[data-theme-id="<metadata.id>"]`，两处不一致时导入不通过。
  改完后导入 `qa-theme/` → installed 清单应出现 `qa-theme`（导出 -> 编辑 -> 导入）。

## E 移除用户数据（onefile）

- E1 确认入口只在 onefile 出现：onedir 与源码运行不应出现该按钮。
- E2 点开确认对话框：应列明将删除 profile / assets / runtime；确认键初始不可点，5 秒倒计时结束前
  仍不可点；取消键始终可用，取消后页面仍可用。
- E3 倒计时结束后确认：进程退出；`profile/`、`assets/`、`runtime/` 全部消失；空根目录被移除；
  `MarkdownReader.exe` 本身仍在。
- E4 删除后再次启动同一个 EXE：回到默认设置、没有旧外置主题、生成新的日志（旧数据没有复活）。

## F 升级路径

- F1 旧 `template` 不得复活：在 EXE 同级放一个旧版 `config.json`，其中**至少**包含
  `template: "office"`、`output`、`external_themes`。首次启动应用 → 这些兼容数据按迁移规则进入
  `profile/config.json`，旧文件按既定语义退场。此时必须同时成立：① GUI 里**没有**内置主题选择器；
  ② 转换仍使用 bridge 的 `BOOTSTRAP_TEMPLATE = "modern"`（生成 HTML 的 `html[data-theme-id]`
     是 modern）；
  ③ 阅读端主题仍由 Viewer 的 `localStorage["markdownreader-theme-id"]` 偏好决定；HTML 自身带有的
     `data-theme-id="modern"` 只是**没有有效保存偏好时的 bootstrap fallback**；
  ④ 迁移完成后修改那个旧文件不再产生任何影响。
- F2 迁移完成后再修改那个旧文件 → 不再影响当前配置（旧配置不复活）。

## G 打印（真实 Edge）

- G1 Edge 打印预览（Ctrl+P）：页边距与旧版一致；正文列主题块与左右两条框线正常。
- G2 导出 PDF 翻页检查：表格、代码块、长文档分页可接受。

## H 安全

- H1 首次双击 onefile 时记录 Defender / SmartScreen 的实际表现：没有 malware detection 即为通过；
  unknown-publisher / reputation 提示按实际情况记录，不要求完全没有提示。


全部通过后，把 `__CHECKLIST_PATH__` 里的全部条目勾选，并写下结论行「QA 结论：通过」
（`release_freeze.py` 按字面量匹配，这七个字必须完整出现）。该文件的 `QA identity` 块必须与当前
版本和当前 production renderer 一致 —— gate 就是按它发现记录的，v1 时代的记录因为没有身份块
而无法被复用。然后：

    git add __CHECKLIST_PATH__
    git commit -m "docs: record the __VERSION__ acceptance run"
    git push origin main
    python packaging/release_freeze.py --check-only
    python packaging/release_freeze.py --tag --artifact-dir "<exact candidate dist directory>"
"""


def render_guide(dist_dir: str = "dist") -> str:
    """Render the operating guide for the version and candidate directory in this checkout."""
    return (
        GUIDE.replace("__VERSION__", DISPLAY_VERSION)
        .replace("__CHECKLIST_PATH__", CHECKLIST_PATH.as_posix())
        .replace("__DIST_DIR__", dist_dir)
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the acceptance material outside the repository."
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--dist-dir",
        default="dist",
        help="directory containing the exact candidate artifacts",
    )
    parser.add_argument("--force", action="store_true", help="replace an existing directory")
    args = parser.parse_args()

    target = Path(args.output).expanduser()
    if target.exists() and not args.force:
        print("目标目录已存在：" + str(target))
        print("如需重建，请加 --force（会先删除该目录）。")
        return 1
    if target.exists():
        shutil.rmtree(target)

    build_documents(target)
    build_themes(target)
    artifact_dir = Path(args.dist_dir).expanduser()
    if not artifact_dir.is_absolute():
        artifact_dir = ROOT / artifact_dir
    write(target / "操作指引.md", render_guide(str(args.dist_dir)))

    exe = artifact_dir / f"MarkdownReader-{DISPLAY_VERSION}-win-x64.exe"
    print("素材目录：" + str(target))
    print("主题标本：" + str(target / "主题标本"))
    print("操作指引：" + str(target / "操作指引.md"))
    print(
        "被测 EXE："
        + (str(exe) + "（存在）" if exe.is_file() else "dist 下尚未找到，请先构建或以源码运行")
    )
    print(
        "提示：验收记录提交到仓库后，用 --tag --artifact-dir 指向已验收候选包目录；"
        "该步骤会复核哈希并复用原产物。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
