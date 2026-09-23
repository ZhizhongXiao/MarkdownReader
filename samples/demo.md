---
title: MarkdownReader 阅读示例
tags:
  - 排版
  - 公式
  - 图片
  - 脚注
author: MarkdownReader
draft: null
weight: 1
summary: |
  本文是渲染能力的标本。
  转换结果保存在同目录的 demo.html，可直接对照。
---

# MarkdownReader 阅读示例

本文是渲染能力的标本：内容覆盖当前受支持的 Markdown 与 HTML 写法，转换后可直接对照同目录的 `demo.html`。
它用来观察排版、导航与打印的实际效果，不是使用教程。

## 文字与行内元素

正文支持**重点强调**、*斜体说明*、~~删除线~~和 `行内代码`，中英文与数字 2026 可以混排。

- 裸文件名保持文本：`README.md`、`report.md`、`版本 1.2.3`。
- 真链接保持可点：[MarkdownReader 仓库](https://github.com/ZhizhongXiao/MarkdownReader)。
- 裸网址同样会识别：https://example.com

### 长链接与长 token 的折行

下面两个 token 会在容器内折行，不会被裁掉：

https://github.com/ZhizhongXiao/MarkdownReader/blob/main/docs/QA-CHECKLIST.md?plain=1&tab=readme-ov-file#qa-%E7%BB%93%E8%AE%BA

`zh_CN_an_identifier_long_enough_to_prove_that_a_single_token_wraps_inside_the_column`

### 标题里的 <code>行内代码</code> 与 <span>HTML</span>

标题允许行内元素；左侧目录保留同样的文本，不会显示标记本身。

## 段落、引用与分隔线

> 专注内容，按需选择版式：左侧目录用于定位，顶部工具栏用于调整展开层级、切换明暗模式、开启自动编号或打印。

引用块可以包含**强调**与 `行内代码`，也可以跨多行书写。

---

## 列表

整理资料时常用有序列表：

1. 用标题组织章节。
2. 用表格比较信息。
3. 用代码块保留操作示例。
4. 用脚注补充背景。

无序列表与嵌套：

- 学习笔记
  - 概念梳理
  - 公式与例题
- 工作文档
  - 操作说明
  - 阶段总结
    - 更细的层级

## 表格

| 模板 | 阅读风格 | 适用内容 | 换行与折行 |
| --- | --- | --- | --- |
| Modern | 舒展、清爽的通用排版 | 学习笔记、长篇资料 | 单元格内的长文本按列宽折行 |
| Office | 类 Word 的正式文档排版 | 报告、制度、打印材料 | 保留首行缩进与固定行距 |
| VS Code | 紧凑的技术文档排版 | 开发笔记、配置说明 | 等宽感更强，目录更紧凑 |

## 代码

```python
from pathlib import Path

source = Path("samples/demo.md")
print(f"阅读示例：{source.name}")
print("Budget: $100; remaining: $200")
```

代码块带复制按钮；内容里的 `$` 按字面显示，不会被当成公式。

## 公式

行内公式嵌入解释，例如圆的面积 $A = \pi r^2$，勾股定理 $a^2 + b^2 = c^2$。

$$
\bar{x} = \frac{1}{n}\sum_{i=1}^{n}x_i
$$

公式在本地由 Node.js 与 KaTeX 预渲染；只有文档真的出现公式时，样式与字体才随 HTML 内联。

## 图片

![源文件转换为阅读文档](assets/demo.svg)

本地图片在转换时内嵌为 data URI：把生成的 HTML 单独拷到别处打开，图片仍然显示。
点击图片可打开灯箱，滚轮可放大到 6 倍，任意缩放级别下点击仍可关闭。

## 脚注

在正文保留结论，把补充信息放进脚注可以减少打断。[^scope]

[^scope]: 脚注支持从正文跳转到注释，再通过返回链接回到引用位置。
[^print]: 打印只保留正文：目录、工具栏等交互控件不会出现在纸面上。

第二处引用用于对照跳转与回跳。[^print]

## 原始 HTML（不是 Markdown 扩展）

以下片段是**原始 HTML**，由浏览器直接解释；转换器保留它们，不会把它们当成 Markdown 语法。
这不代表实现了对应的 Markdown 扩展。

- 行内标注：<mark>raw HTML mark</mark>，也可以 <span style="color:#5b7fd4">用 span 着色</span>。
- 折叠区块：

<details>
<summary>展开查看细节</summary>

块级内容同样可以放进 `details`，用于默认收起的补充说明。

</details>

明确不在兼容范围内的写法：`==mark==`、任务列表 `- [ ]`、Callout、Mermaid、WikiLink。
它们保持字面文本，不会被渲染成对应组件。

## 多级标题与目录

### 三级标题

#### 四级标题

##### 五级标题

###### 六级标题

正文标题会生成左侧目录，支持跳转、滚动定位与目录折叠；顶部的展开、折叠按钮按层级调整正文显示范围。
本页包含 H1 至 H6，可用来观察多级目录的层次与缩进。

### 自动编号

顶部工具栏可开启自动编号；本页不在标题里手写序号，便于比较开启与关闭的效果。

## 阅读与打印

- 明暗模式：浅色与深色都可用，切换后刷新仍保持。
- 阅读位置与折叠状态：按文档分别记录，重新打开同一文档会恢复。
- 打印：纸面为白纸，主题的浅蓝底与左右两条框线画在正文列上；关闭打印对话框里的「背景图形」只丢蓝底，框线保留。
- 表格与代码块：过宽时在容器内横向滚动。

---

*本文是渲染能力标本：能力范围变化时同步调整本文，并重新生成 `demo.html`。*
