# G0 基线冻结

记录改造前的源码身份、渲染回归门禁和启动/转换耗时。性能数字是本机源码运行基线，不作为最终性能门槛。

## 基线身份

- 仓库：<https://github.com/ZhizhongXiao/MarkdownReader>
- 分支：`main`
- 基线提交：[`ee6090bfb5a5e0aaaa11a353252a607921d3571a`](https://github.com/ZhizhongXiao/MarkdownReader/commit/ee6090bfb5a5e0aaaa11a353252a607921d3571a)
- `vscode-office` submodule：`908258dafc827ce0475fe7671d414914fbd3867b`
- 环境：Windows、Python 3.12.10、Node.js v24.20.0

当前工作目录来自 GitHub ZIP，原下载不带根仓库 Git 元数据。基线核验将根仓库接回上述 `main` 提交，确认项目文件与该提交一致，并恢复 ZIP 中缺失的受跟踪文件 `samples/demo.html`。本次改造不修改 `upstream/vscode-office/`。

## 渲染行为门禁

- Markdown 样例：`samples/demo.md`。
- HTML 冻结样例：`samples/demo.html`。
- 门禁：`tests/test_demo_generation.py::test_demo_html_matches_the_committed_specimen`，逐字节比较新生成 HTML 与冻结文件。
- 兼容和转换覆盖由完整 Python 测试套件及 renderer Node 测试套件提供。

改造前，完整 Python 回归为 **807 passed、1 skipped**；`renderer/` 的 Node 测试为 **91 passed、0 failed**。加入计时日志后，完整 Python 回归为 **809 passed、1 skipped**（233.93 秒），目标子集为 **22 passed**。回归也触发 Viewer、GUI 和索引页的 jsdom 行为契约。Node renderer 源码未修改。一轮完整回归曾有一个本机 loopback 图片请求失败；该用例单独重跑通过，随后完整回归重跑通过。

## 当前耗时基线

测量输入为 `samples/demo.md`，输出写入临时目录，关闭远程资源抓取。首次生成的 HTML 与 `samples/demo.html` **字节完全相同**。启动和转换数值均为单轮观察值；连续请求共在同一个 Python 进程内运行。

| 项目 | 耗时 | 备注 |
| --- | ---: | --- |
| GUI 冷启动至 WebView `loaded` | 5,878.58 ms | 源码模式；从 Python 测量入口计时，包含 Node 版本探测和 renderer smoke；隔离临时 profile |
| GUI 新 profile 复测至 WebView `loaded` | 3,873.19 ms | OS 文件缓存已预热；应用自身 `gui_ready` 日志为 3,630.52 ms（从 `gui.app.main` 入口计时） |
| Node 版本探测 | 133.23 ms | 首次转换中的 `node --version` 子进程 |
| 首次 renderer smoke | 691.37 ms | 离线 KaTeX/runtime 校验 |
| 首次正式 renderer 请求 | 596.02 ms | 包含 Node 启动、Markdown 渲染和资源处理 |
| 首次 HTML assembly | 117.90 ms | Python 装配阶段 |
| 首次输出写入 | 7.29 ms | 不含上游渲染与 assembly |
| 首次完整转换 | 1,599.11 ms | 从 `process_single` 调用前计时 |
| 连续请求 2–6 | 569.52、286.37、228.48、214.01、193.25 ms | 中位数 **228.48 ms**；当前每次请求仍会启动一个正式 renderer Node |

首次转换共创建 3 个 Node 进程：版本探测、smoke、正式渲染。连续请求各创建 1 个 Node 进程。请求 2–6 的耗时下降受系统文件缓存和运行时预热影响，不代表隔离的稳定性能分布。

GUI 成功触发页面 `loaded` 并自动关闭。WebView2 在测试结束时有一次 Crashpad 临时目录清理竞态；该临时目录随后已单独清除。GUI 数字因此反映页面 ready 时间，不是打包 EXE 的冷启动数据。

## 计时日志

G0 加入仅供诊断的 DEBUG 计时日志，不向渲染协议或 HTML 写入计时数据：

- `node_version_probe`、`renderer_artifact_ready`、`renderer_process`、`renderer_smoke_ready`
- `renderer_total`、`html_assembly`、`output_write`、`conversion_pipeline`
- `gui_ready`

资源解析和内嵌在 renderer Node 调用内部，因此当前记录在 `renderer_process` 总时长中，尚未单独拆分。GUI 主程序启用 DEBUG 日志；查看运行日志可比较这些阶段。G0 不设耗时门槛。后续阶段将用相同样例和方法比较，并继续以 demo 字节快照作为渲染结果门禁。

## G1：首次 renderer 启动门禁

首次 Node renderer 请求携带单独的离线 KaTeX smoke 输入；`renderer/entry.js` 在同一进程先运行 smoke，再渲染实际 Markdown。Python 检查 smoke 是否产生 KaTeX HTML 和样式、无 author references、无 warnings，然后从返回对象移除内部验证字段。协议版本仍为 v2，常规请求 envelope 不增加字段。

GUI 启动只检查 Node 版本和 renderer artifact，不再为 smoke 单独启动 renderer。首次实际转换因此只创建一个 renderer 子进程；Node 版本探测仍是独立的轻量进程。后续请求保持 one-shot，每次各启动一个 renderer；Session 复用属于 G2。

G1 验收记录：`renderer/` 的 `npm test` 为 **91 passed、0 failed**；G1 定向 Python 回归为 **44 passed**；完整 Python 回归为 **810 passed、1 skipped**（236.88 秒）。Python 静态检查覆盖 7 个修改文件，syntax、Ruff、Pyright 均为零错误。新增桥接用例确认首次请求只调用一次 renderer 子进程，并在该请求中携带离线 smoke；真实 renderer 转换仍由 demo 快照测试逐字节核对 `samples/demo.html`。版本探测仍是单独的 Node 子进程，Node 长连接尚未实现。
