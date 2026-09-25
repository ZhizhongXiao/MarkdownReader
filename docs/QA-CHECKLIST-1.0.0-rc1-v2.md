# MarkdownReader 1.0.0-rc1（v2 production renderer）实机验收清单

这份记录对应 **Cutover C4 之后**的 production renderer（v2：`renderer/dist/renderer.cjs` +
`core/html_assembly.py`）。`docs/QA-CHECKLIST.md` 保留为 v1 production 的历史证据，两者不能互相替代：
`packaging/release_freeze.py` 只认这一份（用 `--qa-record docs/QA-CHECKLIST-1.0.0-rc1-v2.md`）。

在目标机器上按顺序执行；每一项都记录实际结果，不通过就停下修，不带着已知问题发布。

只有在结论处写下 `QA 结论：` 接 `通过`，并且把清单里的全部条目勾选，`packaging/release_freeze.py`
才会允许打 tag。

## A. 启动与外壳

- [ ]  onefile：双击 `MarkdownReader-1.0.0-rc1-win-x64.exe`，启动图出现后 GUI 正常显示
- [ ]  没有系统 Node.js 的机器上仍能启动（EXE 只使用内置 Node）
- [ ]  frozen 启动检查走 v2：删掉（或临时改名）包内的 `_internal/renderer/dist/renderer.cjs`，应用必须**启动即失败**并给出可读提示，而不是转换到一半才报错
- [ ]  普通用户权限（非管理员）可启动、可转换
- [ ]  中文路径与含空格路径下的输出目录均可写入
- [ ]  `config.json` 首次保存设置时生成在 EXE 同级目录；重启后设置恢复

## B. 输入与转换

- [ ]  原生文件窗口添加文件；Ctrl / Shift 多选
- [ ]  拖入文件、拖入目录
- [ ]  单文件转换
- [ ]  目录批量转换：勾选「保留目录结构」后子目录被保留，且整套产物落在「输出目录/源目录名-HTML/」下；不勾选则全部平铺
- [ ]  批量索引页生成并能打开
- [ ]  Modern / Office / VS Code 三套模板各转换一次

## C. 文档特性（v2 renderer）

- [ ]  YAML front matter：页面标题取自 `title`，原始 `---` 块不出现在正文里
- [ ]  行内公式与块级公式（KaTeX）
- [ ]  本地图片（内嵌为 data URI，移动 HTML 后仍显示）
- [ ]  脚注
- [ ]  清单内跨 Markdown 链接正确指向生成的 HTML
- [ ]  无公式文档不含 KaTeX 字体（记事本搜 `KaTeX_AMS` 为 0 处）；含公式文档字体完整
- [ ]  **TARGET：任务列表 checkbox** 渲染为可勾选控件，字面 `[ ]` 不残留
- [ ]  **TARGET：`==高亮==`** 渲染为 `<mark>`，字面 `==` 不残留
- [ ]  **TARGET：Callout**（`> [!NOTE]` / `> [!WARNING]`）渲染为提示块，标记文本不残留
- [ ]  **TARGET：WikiLink**（`[[第二章]]`、`[[第二章|别名]]`）渲染为指向目标的链接
- [ ]  **TARGET：Obsidian tag**（`#标签`）渲染为标签语义，不是普通文本
- [ ]  **TARGET：Mermaid** 围栏在阅读器里离线渲染出图形（断网/断 Wi-Fi 后刷新仍能渲染）
- [ ]  **TARGET：PlantUML**（`@startuml` 块或 `plantuml` 围栏）在联网时显示图形

## D. 阅读器

- [ ]  目录导航与跳转（点击目录项跳到对应小节；高亮跟随视口顶部）
- [ ]  正文逐条折叠
- [ ]  刷新后折叠状态与阅读位置恢复
- [ ]  目录折叠状态保留
- [ ]  代码复制按钮
- [ ]  图片灯箱：打开 / 关闭正常；滚轮可缩放至 6 倍，缩放后仍可点击关闭
- [ ]  明暗模式切换并保持
- [ ]  自动编号开关

## E. 索引页

- [ ]  搜索命中与不命中
- [ ]  复制绝对路径（本地盘；如有网络共享，另测 UNC）
- [ ]  文件夹折叠

## F. 打印

- [ ]  Edge 打印预览：页边距与旧版一致；正文列主题块与框线正常
- [ ]  导出 PDF 正常
- [ ]  表格、代码块、长文档分页可接受

## G. 安全性

- [ ]  Defender 对 onefile 的实际表现（首次运行是否被拦、是否需要放行）

## H. 打包与回退

- [ ]  onedir 包内同时存在 `_internal/renderer/dist/`（v2 载荷）与 `_internal/node_renderer/`（v1 回退资产）与 `_internal/node/node.exe`
- [ ]  按 `packaging/README.md` 的 rollback 说明（把 `core/config.py` 的 `PRODUCTION_RENDERER_VERSION` 改回 `"v1"` 并重建）后，转换产物仍正常；改回 `"v2"` 重建后恢复
- [ ]  内置 Node 版本满足 v2 下限（`v24.20.0` ≥ 18）

## 结论

- 测试机器：
- Windows 版本：
- 测试人：
- 日期：
