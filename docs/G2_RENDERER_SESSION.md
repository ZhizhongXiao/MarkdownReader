# G2 Renderer 长连接

## 范围与生命周期

G2 基于 G0/G1 提交 `da3fe675406193e77026e6c63f3a5749c56dee8e`，保持 Markdown、Viewer、Theme 和
HTML assembly 语义。新增代码只使用 Python 与 Node 标准库，无新增依赖或 HTML 载荷。

```text
同一个 Python 进程（当前 GUI / core，将来 Backend）
  → renderer_node：Node 版本和 artifact 预检
  → renderer_v2：共享 Session、串行调度、每个 Node generation 的 smoke 和 v2 校验
  → RendererSession：Popen + stdin/stdout JSONL
  → renderer.cjs --server：顺序响应，每次 createRenderer(options)
  → Python assembly：输出原有 standalone HTML
```

- 首次真实转换才启动一个 renderer Node；离线 KaTeX smoke 与文档位于同一请求、同一 Node 生命周期。
- 连续转换和同进程多个线程共享一个 Session，warm 请求不再次创建 Node。
- `node --version` 仍是独立的轻量预检进程，不执行 renderer。
- 每次请求新建 markdown-it renderer、tokens、env、本地/远程资源 reader；模块加载复用。
  KaTeX/Mermaid 资产缓存在每个外部请求开始时清空，保留 one-shot 对资产变化和失败 warning 的行为。
- Session 只提供进程启动、请求收发、关闭；`start()` 发现旧进程已退出时先回收再重建，返回新的 generation。
  smoke 验证绑定 Session 和 generation，重建后的首次请求必须重新校验。
- `close_renderer_session()` 和 Python `atexit` 会关闭 stdin，等待 Node 正常退出；超时则终止并回收。
  stdout 收发线程与 stderr 排空线程随进程一起收尾。正常关闭可重复调用。
- 请求的写入和响应读取共用 120 秒等待上限；这是请求超时，**不是空闲退出计时**。
  请求超时、EOF、无效 JSON 或响应 ID/协议不匹配会关闭该子进程，错误交给调用方。
  生产 bridge 遇到 v2 envelope/渲染失败也会关闭该 Session；下一次请求重新启动并 smoke。

当前 G2 的 Node 跟随 Python 宿主生命周期；G3 引入独立 Backend，G4 在 Backend 中实现 120 秒空闲退出。
当前失败的在途请求不会自动重放，G9 再完善一次自动重试与服务级故障恢复。

## JSONL 传输协议 v1

该协议只用于 Python 与直属 Node 子进程的 stdin/stdout。每行恰好一个 UTF-8 JSON 对象；
Markdown 中的换行由 JSON 转义，stdout 无日志。未来 Named Pipe Backend IPC 是独立协议。

请求：

```json
{"protocol":1,"id":"1","request":{"markdown":"# 标题\n","options":{"fetch_remote_resources":false},"context":{}}}
```

响应：

```json
{"protocol":1,"id":"1","response":{"protocol_version":2,"ok":true,"html":"...","headings":[],"features":{},"warnings":[],"resources":{"items":[],"styles":[],"scripts":[],"author_references":[]}}}
```

外层 `protocol=1`、非空 string `id` 必须匹配；内层继续使用现有 v2 成功/错误 envelope。
首次请求可携带 G1 的 `runtime_validation`，其内部响应由 bridge 验证后剥离，不进入 assembly 或 HTML。
错误请求返回对应 ID 的 v2 error envelope；无法取得合法 ID 时为 `null`。server 继续读取下一行。
关闭 stdin 表示结束服务，已接收请求按序完成，输出写完才退出。

`node renderer.cjs` 的 one-shot 格式和 `--info` 保留，二者与 server 共用 `render_request.js` 的渲染函数。
打包 spec 使用的 `validate_v2_runtime()` 构建自检入口也通过同一个 Session 执行离线 smoke。

## 验收覆盖

- 连续 6 次 `generate_demo()`：记录实际 `Popen` 次数和 PID，正式 renderer 恰好一个；每个 HTML 均与
  `samples/demo.html` 逐字节相同，显式关闭后子进程退出码为 0。
- 12 个请求由 4 个 Python 线程并发调用：正式 renderer 恰好一个，各响应与对应输入匹配。
- 全部 Markdown fixture 在一个 Session 中顺序转换，完整 envelope 与逐次 one-shot 相等。
- 交替 math on/off、重复 heading/footnote、Mermaid、大体积资源、中文和空格路径、warning，检查状态不串用。
- 更新本地图片、KaTeX CSS 和 Mermaid metadata 后，warm 响应继续等于新 one-shot，warning 不被旧缓存隐藏。
- JSONL 顺序、请求 ID、错误请求后继续转换、EOF 输出排空；阻塞写超时、大 stderr、损坏响应均有界失败并回收。
- 真实 Node 被终止后，下次转换重建并重新 smoke；关闭后可显式重启，线程与管道完成清理。
- 实际执行打包 spec 的 `_v2_smoke_source` 片段，覆盖构建入口存在性与运行行为，不启动 PyInstaller 或 GUI EXE。

```powershell
cd renderer
npm test
cd ..
uv run pytest -q tests/test_renderer_session.py tests/test_renderer_v2_bridge.py tests/test_node_runtime.py tests/test_g0_timing.py tests/test_demo_generation.py
uv run pytest -q
```

G2 计时日志新增 `node_spawn`（含 PID），每次请求使用 `renderer_request`；G0 的
`renderer_process` 是当时 one-shot 的历史字段，其余 core/assembly/GUI 计时保持可用。
本阶段以进程复用与输出等价为门槛，G10 再制定完整性能验收数据。

## 2026-10-08 验收结果

- Python G2 专项：**14 passed**（17.68 秒），包括真实进程计数、所有 fixture 对照、demo 字节快照与清理。
- 完整 Python 回归：**824 passed、1 skipped**（141.12 秒）。
- renderer `npm test`：**93 passed、0 failed**，构建时 pin 与 upstream checkout 校验一致。
- `python_review`：6 个修改/新增 Python 文件，syntax、Ruff、Pyright 均为零错误，scope complete。
- demo 标本、Viewer、Theme 和 upstream 文件无修改；`git diff --check` 通过。

构建链检查发现 G1 移除了 spec 仍在使用的 `validate_v2_runtime()`。G2 恢复了该构建自检入口并接到共享
Session；回归实际运行 spec 生成的 Python 自检命令。当前结果不包含新打包 EXE 的实机验收。
