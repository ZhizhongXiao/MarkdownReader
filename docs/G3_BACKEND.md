# G3：Backend 服务宿主

## 边界

`backend.service.Backend` 是无 GUI 的转换服务宿主。它在构造时不读取配置、不检查 Node，也不启动
renderer。每个 Backend 拥有自己的 `RendererBridge`；首次有效转换时创建一个 `RendererSession`，后续转换
复用该 Session。调用 `close()` 或退出上下文时关闭并回收自己拥有的 Node。

Backend 将配置路径交给 `core.config.load_config`，并将单文件转换委托给现有的
`core.converter.process_single`。转换计划、Markdown 解析、资源处理和 HTML assembly 仍由 core 完成。
`process_single` 的 `renderer` 参数用于注入 Backend 自有的渲染函数；既有调用不传该参数时，继续走默认
renderer bridge。

## 请求协议

Python API 与传输层解耦，协议版本为 1。当前只接受 `status` 和 `convert`：

```json
{"protocol":1,"id":"42","method":"status","params":{}}
```

```json
{"protocol":1,"id":"43","method":"convert","params":{"input_path":"D:\\Notes\\a.md","output_path":"D:\\Notes\\a.html","overwrite":true,"offline":true}}
```

成功响应包含相同的请求 ID 和 `result`。失败响应包含 `error.code` 与 `error.message`。`convert` 的输入
和显式输出路径必须是绝对路径；未提供输出路径时，Backend 使用 Markdown 同目录、同名 `.html`。输出仅接受
`.html` / `.htm`，不能覆盖源文件。`overwrite` 可在单个请求中指定；未指定时沿用配置。`offline` 默认为
`false`，为 `true` 时关闭远程资源抓取。

Backend 在同一实例内串行处理请求，所以 RendererSession 与 Python core 的文件转换不会交叉执行。不同
Backend 实例目前彼此独立；系统单实例约束及客户端间共享要由 G5/G6 的本地 IPC 与 ownership 实现。

## 命令行

```powershell
python -m backend status
python -m backend convert path\to\note.md --output path\to\note.html --offline
```

CLI 适合独立检查和单文件转换。每次 CLI 调用都会退出并回收 Node；它不充当常驻服务，不提供 120 秒
空闲计时，也不载入 GUI。G4/G5 加入宿主生命周期与 Named Pipe 后，GUI 和其他本地客户端会连接同一
Backend 实例。

## G3 验收

- 新 Backend 的 `status` 返回当前 Backend PID，且 `renderer_pid` 为空；不会启动 Node。
- 独立 Python 子进程导入并使用 Backend 时不载入 `gui` 模块。
- 同一 Backend 连续转换 demo 三次，仅创建一个 `renderer.cjs --server` 进程；三份输出均与
  `samples/demo.html` 字节一致。
- 关闭 Backend 后，其 RendererSession 子进程正常退出；默认 core bridge 不会被 Backend 关闭或占用。
- 无效版本、方法、参数及已关闭的 Backend 都返回协议化错误。
