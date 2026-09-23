# Node 渲染器

MarkdownReader 的 Markdown 渲染服务，npm 包标识为 `markdownreader-node-renderer`。

## 依赖与安装

```bash
cd node_renderer
npm ci
```

- markdown-it：解析与渲染
- markdown-it-footnote：脚注与返回链接
- markdown-it-texmath 与 katex：行内与块级公式，不使用 CDN

## 调用协议

Python 通过子进程调用，Windows 下由桥接层隐藏子进程窗口。从标准输入读 JSON，向标准输出写 JSON：

```json
{"markdown": "# 标题\n\n**粗体**", "options": {"html": true, "math": true}, "context": {}}
```

```json
{"html": "<h1>标题</h1>\n<p><strong>粗体</strong></p>", "headings": [{"level": 1, "text": "标题", "anchor": "标题"}], "warnings": [], "assets": {"css": ""}}
```

- `headings` 供 Python 生成目录：标题文本、锚点与用于目录的行内 HTML。
- `assets.css` 只在文档真的出现公式时携带自包含的 KaTeX 样式（展开后的字体 base64 约 1.4 MB）。
- `context` 携带源文件、输出文件与本次转换的文档映射，用于把清单内的 `.md` / `.markdown` 链接
  改写成生成的 HTML。
- `warnings` 是给人看的消息：路径以可读形式给出，不做 percent-encoding。

渲染选项与支持的写法见 [兼容范围](../docs/MARKDOWN.md)。

## 自检

```bash
echo '{"markdown":"# Test","options":{}}' | node render.js
```
