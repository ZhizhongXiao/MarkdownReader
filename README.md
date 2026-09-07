# MDViewer

MDViewer 是一款离线 Markdown 转 HTML 阅读器生成工具。

它将一个或多个 Markdown 文件转换为适合阅读、导航和打印的独立 HTML 文档。
生成结果包含所需的 CSS 与 JavaScript，无需服务器、CDN 或网络连接。

> 当前项目已完成最终打包前标准回归，适合作为个人正式版候选或内部发布候选使用，暂不作为公开开源项目发布。

## 功能概览

- 单文件、Windows 原生多选与目录批量转换
- 资源管理器拖放、转换前清单与逐文件状态
- H1 至 H6 多级目录、跳转与滚动定位
- 正文和目录折叠
- 图片点击放大
- 代码复制
- 超宽表格与长代码横向滚动
- 行内公式与块级公式服务端渲染
- Markdown 脚注和清单内跨文档链接重写
- 明暗主题、自动编号与打印优化
- 批量文档索引
- Modern、Office、VS Code 三种阅读模板

## 效果截图

### GUI

![MDViewer GUI](docs/screenshots/gui_main.png)

### Modern

![Modern 模板效果](docs/screenshots/demo_modern.png)

### Office

![Office 模板效果](docs/screenshots/demo_office.png)

### VS Code

![VS Code 模板效果](docs/screenshots/demo_vscode.png)

## 普通用户

普通用户建议直接使用打包后的 `MDViewer.exe`。

基本流程：

1. 打开 `MDViewer.exe`。
2. 单选/复选 Markdown 文件，选择文件夹，或从资源管理器拖入文件和文件夹。
3. 选择输出目录。
4. 选择模板：`modern`、`office` 或 `vscode`。
5. 按“开始转换”。
6. 在浏览器中阅读生成的 HTML。

正式发布的 EXE 支持内置 Node.js。内置后，普通用户无需再安装 Python、Node.js 或 npm 依赖。

配置会在点击“开始转换”后保存到 `MDViewer.exe` 同级目录的 `config.json`，下次启动时自动恢复。

## 开发者

源码运行需要本机安装：

- Python 3.11 或更高版本
- Node.js，且 `node` 命令可从 `PATH` 调用
- Microsoft Edge WebView2 Runtime

安装 Python 依赖：

```powershell
pip install -r requirements.txt
```

安装 Node 渲染依赖：

```powershell
cd node_renderer
npm install
cd ..
```

启动 GUI：

```powershell
python main.py
```

运行自动化测试：

```powershell
python -m pytest -q
```

## 输出规则

### 单文件转换

输入：

```text
notes/demo.md
```

输出：

```text
输出目录/demo.html
```

生成的 HTML 是单文件阅读页，内置样式、脚本、目录、正文和必要资源引用。

### 多文件复选

点击“添加文件”后，可在 Windows 文件窗口中使用 `Ctrl` 或 `Shift` 复选多个
Markdown。也可以从资源管理器直接拖入文件或文件夹。所有实际参与转换的文档会先
显示在右侧“转换清单”中；重复文件自动去重，输出文件冲突会在写入前阻止转换。

### 文件夹批量转换

选择一个文件夹时，程序会递归收集其中的 `.md` 文件。

默认输出：

```text
输出目录/
  文档A.html
  文档B.html
  索引-源文件夹名.html
```

开启“保留目录结构”后：

```text
输出目录/
  源文件夹名-HTML/
    第一章/
      文档A.html
    第二章/
      文档B.html
    索引-源文件夹名.html
```

索引页用于集中跳转到各个生成文档。文档链接默认在新标签页打开，看完后关闭标签页即可回到索引。

### 脚注与跨文档链接

源文档可以直接链接其他 Markdown：

```markdown
参见[第20章](./第20章.md#第二节)。

计量方法[^chapter]

[^chapter]: 参见[第20章](./第20章.md)。
```

当目标 Markdown 同样位于本次转换清单中时，链接会按照实际输出位置改写为 `.html`。
文档内 `#锚点`、网络链接和已经写成 `.html` 的旧链接保持不变。目标存在但没有加入
转换清单时，程序保留原链接并在转换清单和日志中给出警告。

### 覆盖规则

当前生成时会写入目标 HTML 路径；如果目标文件已存在，会被新的生成结果覆盖。

## 模板

| 模板 | 定位 |
| --- | --- |
| `modern` | 清爽、舒适的通用阅读主题 |
| `office` | 类 Word 的正式文档与打印主题 |
| `vscode` | 类 VS Code Markdown Preview 的技术阅读主题 |
| `default` | 供其他模板继承的共享基础模板 |

`default` 提供共用的 `viewer.html`、`viewer.css`、工具栏、目录外壳和兼容变量。
个性化模板只覆盖必要的主题变量和视觉规则。

自定义模板可通过 `metadata.json` 继承基础模板：

```json
{
  "id": "mycompany",
  "name": "My Company",
  "version": "1.0.0",
  "description": "公司文档主题",
  "extends": "default"
}
```

在同一目录添加 `theme.css` 即可。不要复制 `viewer.js` 或另建阅读器。

## 打包

构建单文件 Windows EXE：

```powershell
python -m PyInstaller --clean --noconfirm --workpath "packaging\.pyinstaller-build" --distpath "dist" packaging\MDViewer.spec
```

该命令会把 PyInstaller 的中间构建缓存放在 `packaging/.pyinstaller-build/`，最终产物输出到 `dist/MDViewer.exe`。这样可以避开默认 `build/` 目录可能出现的权限占用问题，同时仍然把缓存和输出保留在项目文件夹中，便于检查和清理。

发布前如需确保没有旧产物残留，可以先删除 `dist/`，再重新执行上面的打包命令。`packaging/.pyinstaller-build/` 是构建缓存，打包完成后可以安全删除。

发布给普通用户前，需要把 Windows 便携版 Node.js 放入：

```text
packaging/node/node.exe
```

打包后的 EXE 会优先使用内置 Node；如果未内置，则回退到系统 `PATH` 中的 `node`。当前项目已按该结构放入并验证过 `packaging/node/node.exe`。

详细说明见 [packaging/README.md](packaging/README.md)。

## 故障排查

### 提示找不到 Node.js

源码运行时，请确认已经安装 Node.js，并且 PowerShell 中可以执行：

```powershell
node -v
```

打包运行时，请确认打包前已放入：

```text
packaging/node/node.exe
```

### 公式没有渲染

公式由 Node 渲染器处理。请确认：

- `node_renderer/node_modules` 已安装。
- 源码运行时执行过 `cd node_renderer && npm install`。
- EXE 打包时已包含 `node_renderer/node_modules`。

### GUI 无法启动或空白

请确认系统安装了 Microsoft Edge WebView2 Runtime。Windows 10/11 通常已经内置或可通过 Edge 组件更新获得。

### 生成后浏览器没有自动打开

请检查 GUI 中“自动打开”是否启用。即使没有自动打开，生成的 HTML 仍会保存在输出目录。

### 打印效果和屏幕显示不完全一致

打印由浏览器打印引擎决定。Office 模板已针对 Edge 打印做过优化，但表格分页、边框和纸张缩放仍可能受浏览器和打印机驱动影响。

## 兼容范围

当前主要面向：

- Windows 10 / Windows 11
- Microsoft Edge / Chromium 内核浏览器
- Python 3.11+
- Node.js 18+ 或随 EXE 内置的 Windows 版 Node.js

生成的 HTML 是离线单文件阅读页，通常可以在现代 Chromium 浏览器中直接打开。打印效果以 Microsoft Edge 为主要参考。

## 项目状态与限制

项目当前处于个人正式版候选、内部发布候选阶段。

已基本稳定的部分：

- GUI 转换流程
- 三套阅读模板
- TOC、跳转、折叠、滚动定位
- 图片、代码块、表格、公式渲染
- 批量索引
- Windows EXE 打包方案

最终发布前仍建议完成：

- 重新打包 EXE 并在干净目录试跑。
- 明确正式版本号和许可证策略。

已知限制：

- 暂未作为跨平台应用设计，主要测试环境是 Windows。
- Node 渲染器仍是必要组成部分；EXE 发布时应内置 Node.js，或要求用户本机安装 Node.js。
- 打印分页无法做到与 Microsoft Word 100% 一致。
- Markdown 原始 HTML 的复杂样式由浏览器自行解释，不保证所有网页级布局都适合打印。
- 当前未提供完整 pytest 自动化套件；后续维护阶段建议补回。

## 项目结构

```text
core/                 Python 调度、配置、目录和文档生成层
gui/                  pywebview 桌面界面
node_renderer/        Node Markdown 渲染器
templates/default/    共享基础阅读器模板
templates/modern/     Modern 阅读主题
templates/office/     Office 正式文档主题
templates/vscode/     VS Code 预览主题
templates/viewer.js   共用浏览器交互逻辑
templates/print.css   共用打印样式
packaging/            PyInstaller 配置与程序图标
docs/                 设计、架构、路线图和截图
tests/                自动化测试预留目录
samples/              Markdown 测试样例
```

## 许可证

当前项目暂不发布为开源项目，也暂未选择开源许可证。

在没有明确许可证文件之前，代码、文档、图标和截图默认保留全部权利，仅供作者本人学习、使用和继续开发。

