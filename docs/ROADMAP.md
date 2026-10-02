# 路线图

当前维护版本：1.0.1。正式验收记录见 [1.0.1 验收清单](QA-CHECKLIST-1.0.1-v2.md)；历史版本记录保留在各自清单中。

本页只写现在与下一步；为什么选择某个方案留在 Git 历史与 [更新日志](CHANGELOG.md)。

## 现在

- v2 renderer 是生产路径；vscode-office 上游版本固定并记录，MarkdownReader adapter 负责资源处理、文档装配与离线交付。
- 每份生成的 HTML 都携带 Modern / Office / VS Code；外置主题可由用户安装并按次选择携带，阅读时主题与明暗模式独立切换。
- 设置页负责外置主题生命周期与用户数据位置；onefile、onedir 都是正式便携构建形态。
- 发布流程要求 onefile 与 onedir 自动校验，并以匹配当前版本与 renderer 的实机验收清单作为 tag 门禁。

## 下一步

### 1. Office 与 VS Code 的兼容清单与增强

- 整理「兼容范围 → 主题表现」的对照清单，明确两套主题各自支持到什么程度。
- 按清单补齐增强：Office 面向打印分页与表格，VS Code 面向长代码与紧凑目录。
- 结论并入 [兼容范围](MARKDOWN.md) 与对应主题的 README。

### 2. 主题制作体验

- 评估是否需要 GUI Theme Builder，用标准参数生成符合现有 CSS-only 主题规范的外置主题。
- 新增主题继续复用唯一 Viewer 外壳与交互，不复制阅读器 JavaScript 或布局。

## 质量目标

生成的 HTML：离线可用、单文件自包含、目录可导航、长文可阅读、打印可接受、不依赖 CDN 与服务器。

桌面程序：普通用户无需安装 Python；正式包无需用户安装 Node；GUI 可稳定完成单文件与批量转换。
