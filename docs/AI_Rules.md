# AI 协作规则

## 编码前

必须完整阅读：

- `docs/DESIGN.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`

如任务涉及打包，还应阅读：

- `packaging/README.md`

如任务涉及模板，还应阅读对应模板目录下的 `README.md` 和 `theme.css`。

---

## 当前项目状态

MarkdownReader 当前处于 1.0.0-rc1 阶段：发布工程已收敛，等待实机 QA 通过后升为 1.0.0。

本阶段优先：

- 稳定
- 收尾
- 文档一致
- 打包可用
- 小范围修复
- 回归验证

避免：

- 大重构
- 重新设计交互
- 新增非核心功能
- 引入新技术栈

---

## 职责边界

不得混淆以下职责：

- Python：调度、文件读写、模板组装、配置、批量索引。
- Node：Markdown 和公式渲染。
- HTML：结构。
- CSS：布局、主题、打印。
- JavaScript：阅读器交互。
- GUI：选择文件、展示预览/日志、调用核心流程。

不得让 GUI 复制 Markdown 渲染、TOC 生成或阅读器交互逻辑。

---

## 禁止事项

不得：

- 随意改变项目架构。
- 随意重命名模块。
- 引入 React / Vue / jQuery / Bootstrap。
- 复制 `templates/viewer.js` 到具体模板。
- 让 Node 直接生成完整阅读器 HTML。
- 让 Python 拼接大段新前端逻辑。
- 修改无关文件。
- 删除用户文件或构建资源而不确认。

---

## 修改原则

优先：

- 小步修改
- 复用现有结构
- 保持单文件 HTML 输出
- 保持模板继承
- 保持 GUI 只调用核心流程
- 保持 Windows 打包可用

避免：

- 难以理解的技巧性代码
- 过大的函数继续膨胀
- 不必要的硬编码
- 为了“整洁”破坏稳定链路

---

## 测试与验证

如果修改核心生成流程，至少验证：

- `core/config.py`
- `core/converter.py`
- `core/index_builder.py`
- `node_renderer/render.js`

如果修改模板，至少运行：

python tools/generate_demo.py

然后人工查看生成的 `samples/demo.html`（该文件不纳入版本控制）。

如果修改 GUI，优先确认 `main.py` 启动和 GUI 资源路径。

如果修改打包配置，确认：

- `packaging/MarkdownReader.spec`
- `packaging/assets/`
- `packaging/node/node.exe`

---

## 完成说明

完成后应说明：

- 修改了哪些文件
- 采用了哪些设计决策
- 验证了什么
- 哪些事项仍未完成
