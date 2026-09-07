# MDViewer Demo

## 项目简介

MDViewer 是一个**离线 Markdown 文档阅读器生成工具**。它将 Markdown 文件转换为独立的 HTML 文档，专为阅读、导航和打印场景优化。

这是 *斜体* 和 _斜体_ 的测试样例。

这是一个行内公式：$a+b=c$ 和块级公式：

$$
E = mc^2
$$

### 原始 HTML 样式保留测试

<span style="background-color: #ffff00;">高亮黄色背景</span>

<span style="color: #9900ff;">紫色文字</span>

<span style="color: rgb(255, 255, 0); background-color: rgb(0, 0, 0);">黄字黑底组合样式</span>

### 核心目标

- 高质量的阅读体验
- 完全离线可用
- 单文件输出，零依赖

## 功能特性

### 核心功能

- Markdown 转 HTML
- 单文件输出，无外部依赖
- 左侧目录导航
- 点击目录跳转
- 滚动同步高亮
- 打印友好
- TOC 折叠与展开
- 正文标题折叠
- 代码块复制
- 图片点击放大
- 阅读位置记忆

## 安装

```bash
pip install -r requirements.txt
```

## 使用方法

```bash
# 确保代码块中的 $ 不会被解析为公式
python main.py demo.md
echo "Total: $100 and $200"
```

## 目录结构

```
MDViewer/
├── main.py
├── renderer.py
├── toc.py
├── config.py
└── template/
    ├── viewer.html
    ├── viewer.css
    ├── viewer.js
    └── print.css
```

## 设计原则

> 一切设计都应提升阅读体验。
> 不要添加仅对编辑有益的功能。

### 单一文件原则

每个 Markdown 文件应生成**恰好一个** HTML 文件。生成的 HTML 必须是**自包含的**，不得依赖：

- 外部 CSS
- 外部 JavaScript
- CDN
- 服务器
- 网络连接

### 职责分离

| 层级     | 职责                       |
| -------- | -------------------------- |
| Python   | 读取、解析、生成 TOC、填充模板 |
| HTML     | 文档结构                   |
| CSS      | 布局、排版、主题、打印     |
| JavaScript | 导航、滚动同步、折叠     |

## 浏览器技术

使用原生浏览器 API：

- `IntersectionObserver` — 实现 Scroll Spy
- `scrollIntoView()` — 实现平滑跳转
- `addEventListener()` — 事件处理
- `navigator.clipboard` — 代码复制
- `localStorage` — 阅读位置记忆

## 版本计划

1. **Phase 1** — 基本阅读器：Markdown 渲染、TOC、ScrollSpy、打印
2. **Phase 2** — 阅读体验优化：折叠、图片放大、代码复制、位置恢复
3. **Phase 3** — 易用性改进：工具栏、暗色模式、自动编号、TOC拖拽
4. **Phase 4** — 多文档支持：批量生成、交叉导航
5. **Phase 5** — 桌面应用：GUI、拖放、EXE 打包

### 1 Phase 1 功能

#### 1.1 基本阅读

#### 1.2 目录导航

#### 1.3 打印支持

### 2 Phase 2 功能

#### 2.1 TOC 折叠

#### 2.2 正文折叠

#### 2.3 代码复制与图片放大

### 3 Phase 3 功能

#### 3.1 工具栏

顶部工具栏提供以下按钮：

- 展开/折叠全部正文
- 展开/折叠全部目录
- 自动编号开关
- 暗色模式切换
- 打印

#### 3.2 暗色模式

支持浅色和暗色两种主题，默认跟随系统设置。切换状态保存到 localStorage。

#### 3.3 自动编号

为标题自动添加层级编号（1、1.1、1.1.1 等）。

截至目前版本，"1 Phase 1 功能" 和 "1.1 基本阅读" 已经包含手动编号，打开自动编号时**不会重复编号**。

#### 3.4 TOC 宽度拖拽

鼠标拖动左侧目录与正文之间的分隔线，可调整目录宽度。宽度保存到 localStorage。

---

*感谢使用 MDViewer！*

一个最后的公式测试：$x^2 + y^2 = z^2$
