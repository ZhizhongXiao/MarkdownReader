"""Prepare the material for the 1.0.0-rc1 acceptance run.

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
import zlib
from pathlib import Path

DEFAULT_OUTPUT = Path.home() / "Documents" / "MarkdownReader-QA-1.0.0-rc1"


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

    sections = []
    for index in range(1, 25):
        sections.append("## 第 %d 节\n\n正文内容，用于滚动、折叠和打印分页测试。\n" % index)
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


ROOT = Path(__file__).resolve().parents[1]

GUIDE = """# MarkdownReader 1.0.0-rc1 实机验收操作指引

被测产物（先确认存在）：

    dist/MarkdownReader-1.0.0-rc1-win-x64.exe
    dist/MarkdownReader-1.0.0-rc1-portable-win-x64.zip   （可选形态；清单只验收 onefile）

在 GUI 里把「本目录」整体作为输入，输出目录另选一个空目录；
模板分别用 Modern / Office / VS Code 各跑一次。
观感基线：正文为左对齐；超长链接与裸文件名会在容器内折行，不会被裁掉；
打印输出为白纸加跟随正文的主题块与左右两条框线。
下面每一条按同一顺序对应 `docs/QA-CHECKLIST.md` 中的条目。

## A 启动与外壳

- A1 双击 onefile EXE → 启动图出现后 GUI 正常显示。
- A2 若本机装有系统 Node：临时把它从 PATH 移开（或换一台没有 Node 的机器）仍然可以启动。
- A3 以普通用户（非管理员）身份启动并完成一次转换。
- A4 把本目录复制到含中文与空格的路径下再跑；输出目录也选中文与空格路径。
- A5 改一次输出目录并转换成功 → EXE 同级出现 config.json；关闭重启 → 设置恢复。

## B 输入与转换

- B1 用「添加文件」原生窗口选 `根文档.md`，按住 Ctrl / Shift 多选
  `甲组/一号.md` 与 `乙组/YAML 全类型.md`。
- B2 把 `根文档.md` 拖入窗口；再把「甲组」目录拖入窗口。
- B3 只保留 `根文档.md` 做单文件转换；它引用的 `甲组/一号.md`、`乙组/YAML 全类型.md`
  不在本次清单内，因此日志里出现「Markdown 链接目标未加入转换清单」提示属于预期，
  且提示里应是可读路径（`甲组/一号.md`），不是 `%E7%94%B2…` 这样的编码；
  这是源文档写下的相对路径，不要求显示盘符。
- B4 整个本目录做批量转换（含子目录），勾选 preserve structure：整套产物落在
  「输出目录/源目录名-HTML/」下，其中应出现 `甲组/一号.html`、`乙组/YAML 全类型.html`、
  `中文 空格 目录/文档 一.html`；不勾选则全部平铺在输出根目录，同名文件会在预检阶段被拦下。
- B5 批量后打开生成的索引页，确认列出了全部文档；自动打开应落在默认浏览器且地址为
  `file:///…`（若 `.html` 的默认应用不是浏览器，自动打开会失败，需先修系统关联）。
- B6 Modern / Office / VS Code 三套模板各转换一次 `根文档.md`。

## C 文档特性

- C1 `乙组/YAML 全类型.md`：页面标题应为「带引号的标题」（引号被剥离），
  front matter 原块（`---`、`list:`、`nested:` 等）不应出现在正文里。
- C2 `根文档.md`：行内公式与块级公式都正常渲染。
- C3 `根文档.md`：转换后把 HTML **单独拷到别处**打开，图片仍显示（已内嵌 data URI）。
- C4 `根文档.md`：两条脚注可跳转与回跳。
- C5 `甲组/一号.md`：转成 HTML 后回链指向 根文档 的 HTML，另一个指向 二号 的 HTML。
- C6 `根文档.md`：正文里的裸文件名（`根文档.md`、`README.md`、`版本 1.2.3`）保持文本，
  不应出现 `http://xn--…` 假链接；同一段里的真网址仍可点击。
- C7 `乙组/YAML 全类型.md` 无公式：生成的 HTML 不含 KaTeX 字体（记事本搜 `KaTeX_AMS`
  应为 0 处）、体积为几十 KB 级；`根文档.md` 含公式，公式样式与体积保持原样。

## D 阅读器（用 `甲组/二号.md` 的 HTML）

- D1 目录导航点击跳转正确。
- D2 折叠若干正文小节。
- D3 记下滚动位置 → 刷新 → 折叠状态与阅读位置都恢复。
- D4 折叠若干目录分支 → 刷新 → 目录状态保持。
- D5 代码复制按钮可用（用 `根文档.md` 的代码块）。
- D6 点击图片 → 灯箱打开与关闭；在灯箱里滚轮可放大（上限 6 倍），任意缩放级别下点击仍可关闭。
- D7 切换明暗模式 → 刷新后保持。
- D8 打开自动编号（配置 numbering 为 true 后转换一次）→ 标题编号出现。

## E 索引页

- E1 搜索「一号」命中；搜索不存在的词显示无结果提示。
- E2 复制文件夹绝对路径，粘贴核对是否为真实路径：须在本机以 file:// 打开索引页后核对，
  用 http 打开时取不到盘符属正常。
- E3 文件夹折叠与展开正常。

## F 打印（用 `甲组/二号.md` 的 HTML）

- F1 Edge 打印预览（Ctrl+P）：页边距与旧版一致；正文列是主题浅蓝底 + 左右两条淡蓝框线，
  长度随正文；关闭打印对话框里的「背景图形」后蓝底消失、框线仍在，属预期。
- F2 导出 PDF 并翻页检查。
- F3 表格、代码块与长文分页可接受。

## G 安全

- G1 首次双击 onefile 时观察 Defender / SmartScreen：是否拦截、是否需要放行。

全部通过后，把 `docs/QA-CHECKLIST.md` 里的全部条目勾选，并写下结论行「QA 结论：通过」
（`release_freeze.py` 按字面量匹配，这七个字必须完整出现），然后：

    git add docs/QA-CHECKLIST.md
    git commit -m "docs: record the 1.0.0-rc1 acceptance run"
    git push origin main
    python packaging/release_freeze.py --check-only
    python packaging/release_freeze.py --tag
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare the acceptance material outside the repository."
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
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
    write(target / "操作指引.md", GUIDE)

    exe = ROOT / "dist" / "MarkdownReader-1.0.0-rc1-win-x64.exe"
    print("素材目录：" + str(target))
    print("操作指引：" + str(target / "操作指引.md"))
    print(
        "被测 EXE："
        + (str(exe) + "（存在）" if exe.is_file() else "dist 下尚未找到，请先构建或以源码运行")
    )
    print("提示：验收记录提交到仓库后再运行 packaging/release_freeze.py --tag。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
