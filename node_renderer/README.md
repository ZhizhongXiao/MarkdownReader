# MarkdownReader Node 渲染器

MarkdownReader 使用的 Node.js Markdown 渲染服务。npm 包标识统一为全小写 `markdownreader-node-renderer`，与 `package.json` 和 `package-lock.json` 保持一致。

## 依赖

- **markdown-it**：Markdown 解析与渲染
- **markdown-it-footnote**：脚注引用、脚注区块与返回链接
- **markdown-it-texmath**：TeX 行内公式和块级公式扩展
- **katex**：服务端公式排版，不依赖 CDN

## 安装

```bash
cd node_renderer
npm install
```

## 调用方式

Python 通过子进程调用渲染器。渲染器从标准输入读取 JSON，并向标准输出写入
JSON。Windows 打包运行时，子进程窗口由 Python 桥接层隐藏，避免 GUI 转换时弹出
额外命令行窗口。

输入：

```json
{"markdown": "# Hello\n\nThis is **bold**.", "options": {"html": true, "math": true}, "context": {}}
```

输出：

```json
{"html": "<h1>Hello</h1>\n<p>This is <strong>bold</strong>.</p>", "headings": [{"level": 1, "text": "Hello", "anchor": "hello"}], "warnings": [], "assets": {"css": "..."}}
```

`headings` 由 Python 层用于生成 TOC；`assets.css` 主要用于内联 KaTeX 样式。
`context` 可携带当前源文件、输出文件和本次转换文档映射，用于只重写清单内的
`.md` / `.markdown` 文档链接。

## 测试

```bash
echo '{"markdown":"# Test","options":{}}' | node render.js
```
