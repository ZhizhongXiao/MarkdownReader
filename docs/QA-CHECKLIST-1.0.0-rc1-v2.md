# MarkdownReader 1.0.0-rc1（v2 production renderer）实机验收清单

## QA 身份

```text
QA identity
version: 1.0.0-rc1
production_renderer: v2
shapes: onefile, onedir
platform: Windows x64
```

这是 **record class identity**：它证明本记录属于这个版本与这个 production renderer，不等于已经验收了某一个
精确候选产物。候选绑定（产物哈希或 source commit）在最终发布前解决，见 Phase 12A-3 / 12C。

这份记录对应 **Cutover C4 之后**的 production renderer（v2：`renderer/dist/renderer.cjs` +
`core/html_assembly.py`）。`docs/QA-CHECKLIST.md` 保留为 v1 production 的历史证据，两者不能互相替代：
`packaging/release_freeze.py` 按 QA 身份块发现本记录，而不是按固定文件名。

人工验收只覆盖自动契约证明不了的风险：frozen 包、真实 Windows GUI / Edge / Defender、跨进程持久化与真实文件
系统生命周期。GT19、LF-only、`invalid` / `installed_invalid` 边界、renderer 语义矩阵、阅读器与索引页状态机、
删除失败语义、内置 Node 下限、onedir 载荷枚举等由自动化契约与 12A-3 的 build/validation gate 承担，不在这里重复。

在目标机器上按顺序执行；每一项都记录实际结果，不通过就停下修，不带着已知问题发布。

只有在结论处写下 `QA 结论：` 接 `通过`，并且把清单里的全部条目勾选，`packaging/release_freeze.py`
才会允许打 tag。

## A. 启动与 Windows 集成（两种形态都要）

- [ ]  onefile：双击 `MarkdownReader-1.0.0-rc1-win-x64.exe`，启动图出现后 GUI 正常显示
- [ ]  onedir：运行 `MarkdownReader\MarkdownReader.exe`，启动图出现后 GUI 正常显示
- [ ]  目标机没有 Python，也没有 Node/npm（或临时把 Node 移出 PATH）→ 仍能启动并完成一次转换（只用内置 Node）
- [ ]  WebView2 Runtime：确认目标机已安装；若缺失，应用给出可读失败，而不是空白窗口或静默退出
- [ ]  普通用户权限（非管理员）可启动、可转换
- [ ]  中文路径与含空格路径：程序所在目录与输出目录各验证一次
- [ ]  【onedir】临时移走 `_internal\renderer\dist\renderer.cjs` → 应用**启动即失败**并给出可读提示 → 复原文件后恢复
      （onefile 不做 `_MEIxxxx` 人工篡改：载荷在临时解包目录里，不是用户可控接口；其完整性由构建期
       REQUIRED_FILES、内置 Node/v2 预检、`validate_release` 与真实启动/转换共同证明）

## B. 打包 smoke

- [ ]  原生文件窗口添加文件；Ctrl / Shift 多选
- [ ]  拖入文件、拖入目录
- [ ]  单文件转换；生成的 HTML 用 Edge 打开：正文、KaTeX 公式、本地图片（data URI）都正常
- [ ]  目录批量转换：勾选与不勾选「保留目录结构」各一次
- [ ]  批量索引页生成并能打开；搜索命中与不命中；复制绝对路径可用
- [ ]  含 Mermaid 的文档在断网状态下刷新仍能渲染
- [ ]  阅读端主题：用 `根文档.md` 生成一次 HTML，在 Edge 里用页面主题切换在 Modern / Office / VS Code 之间切换 →
       立即生效；刷新后仍停在上次选择（阅读偏好存在 HTML 自己的 localStorage）。转换时无需选主题：三套内置主题永远随产物

## C. 存储与生命周期

- [ ]  首次保存设置（或首次成功转换）后 `profile/config.json` 出现在**本形态的用户数据根**；单纯启动不创建；
      重启后设置恢复。onefile `%LOCALAPPDATA%\MarkdownReader\profile\config.json`；onedir `<应用目录>\data\profile\config.json`
- [ ]  设置页「存储信息」：主要信息里的用户数据根与本形态相符（onefile → `%LOCALAPPDATA%\MarkdownReader\…`；onedir → `<应用目录>\data\…`）；
       展开「详细路径」后 config / 外置主题目录 / runtime 三条路径同样正确
- [ ]  日志与 WebView2 数据只在 `<用户数据根>\runtime\` 下；EXE 旁边不出现 `config.json` / `MarkdownReader.log`
- [ ]  【onefile】把 EXE 改名或移到另一目录（含中文空格路径）→ 设置、外置主题与日志历史都还在
- [ ]  【onedir】用户数据只在 `<应用目录>\data\`；把整个应用目录复制到别处运行，设置仍在
- [ ]  【onedir】删除整个应用目录 → 用户数据完全消失（`%LOCALAPPDATA%` 等处无残留）

## D. 外置主题

- [ ]  从本次素材目录导入两个验收标本（`主题标本/qa-ornamented`、`主题标本/qa-no-preview`，即 `samples/qa-themes/` 的副本）
       → installed 清单各出现一项；点 `qa-ornamented` 的行体 → 右侧预览舞台出现该主题配色；
       `qa-no-preview` → 隐藏整张主题示意图；文字说明水平、垂直居中，并填满与默认预览相同的区域
- [ ]  预览与携带互不干扰：点行体只改预览、勾复选框只改携带（「已选 N」随之变化），两者都不移动对方；预览不写 `config.json`
- [ ]  用 `qa-ornamented` 转换 `根文档.md` → 生成 HTML 携带 `theme-qa-ornamented`（装饰资源已内嵌为 data URI）
- [ ]  重启后两个主题仍在 installed 清单、仍可勾选，文件位于 `<用户数据根>\assets\themes\external\<id>\`
- [ ]  设置页卸载 `qa-ornamented` → 安装副本消失；主页该 id 变为 missing（并出现主页「移除」）；已生成的 HTML 不受影响
- [ ]  设置页「导出主题模板」→ 复制该目录、改 `id` 与 CSS 里的 scope 后仍可导入（导出 -> 编辑 -> 导入）

## E. 移除用户数据（onefile）

- [ ]  入口只在 onefile 出现（onedir / 源码运行没有该入口）
- [ ]  确认框列明将删除 profile / assets / runtime；确认键初始 disabled、5 秒内不可点；取消始终可用，取消后页面仍可用
- [ ]  确认后：进程退出；`profile/`、`assets/`、`runtime/` 全部消失；空根被移除；`MarkdownReader.exe` 仍在
- [ ]  删除后再次启动同一 EXE：回到默认设置、没有旧外置主题、生成新的日志（旧数据不复活）

## F. 升级路径

- [ ]  旧 `template` 不得复活：EXE 同级放一个旧 `config.json`（至少含 `template: "office"`、`output`、`external_themes`）→
       首次启动后兼容数据按迁移规则进入 `profile/config.json`、旧文件退场，且同时成立：GUI 没有内置主题选择器；
       转换仍用 `BOOTSTRAP_TEMPLATE="modern"`（HTML 自身 `data-theme-id="modern"` 仅作无有效保存偏好时的 fallback）；
       阅读端主题仍由 Viewer 的 `localStorage["markdownreader-theme-id"]` 偏好决定；改旧文件不再产生影响
- [ ]  迁移完成后修改那个旧文件 → 不再影响当前配置（不复活）

## G. 打印（真实 Edge）

- [ ]  Edge 打印预览：页边距与旧版一致；正文列主题块与框线正常
- [ ]  导出 PDF 正常；表格、代码块、长文档分页可接受

## H. 安全

- [ ]  Defender / SmartScreen：记录 onefile 首次运行的**实际表现**（无 malware detection 即为通过；
      unknown-publisher / reputation 提示按实际情况记录，不要求完全没有提示）

## 结论

- 测试机器：
- Windows 版本：
- 测试人：
- 日期：
- QA 结论：
