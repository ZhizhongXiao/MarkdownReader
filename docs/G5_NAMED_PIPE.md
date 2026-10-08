# G5：本机 Named Pipe IPC

## 服务入口

常驻服务由 `python -m backend serve` 启动；可用 `--config` 指定配置文件，用 `--pipe-name` 指定测试或隔离用
管道名。默认名称为 `\\.\pipe\LOCAL\MarkdownReader.v1`。G6 增加了启动前的 session mutex ownership；竞争启动者连接
现有服务并返回其状态，不创建第二个 `Backend`。服务启动后不加载 GUI，由同一个 `Backend` 拥有 renderer。

客户端经 `backend.named_pipe.request_named_pipe()` 发送一个协议请求。底层连接使用 JSONL UTF-8 帧；服务端也支持
同一连接上的多行请求。每个有效请求对应一行结构化响应，并回显 `protocol` 与 `id`。协议 v1 当前只接受
`status` 和 `convert`，转换与状态响应沿用 G3 的 `Backend.handle_request()`。

## Shutdown 与接入循环

管道 host 的 watcher 调用 `Backend.wait_for_shutdown()`，等待 G4 创建的同一个 Backend shutdown event。该方法在
Node 退出后返回；watcher 随即设置 Win32 stop event。Accept 循环用 overlapped `ConnectNamedPipe` 同时等待新连接
与 stop event；每个连接的 overlapped 读写也等待同一个 stop event。Backend idle shutdown 后，host 不会再创建或
接收新的客户端实例，阻塞的 accept/read/write 会被取消，活动连接线程退出，随后 `serve` 返回并释放 Backend。

`status` 不刷新 120 秒期限；实际 `convert` 完成后刷新期限。测试为 Named Pipe 设置短期限覆盖退出逻辑，生产值仍
由 G4 固定为 120 秒。显式 Backend 关闭也会唤醒相同的 watcher。

## 本机和用户范围

- Pipe 名称只接受 `\\.\pipe\LOCAL\` 下的单个 ASCII 名称分量；拒绝远程 UNC 和嵌套名称。
- `CreateNamedPipeW` 显式设置 `PIPE_REJECT_REMOTE_CLIENTS`，并提供仅授予当前进程 logon SID 与
  `LocalSystem` 的受保护 DACL。匿名、NETWORK 身份和其它登录会话不匹配该 DACL。
- 同一 logon SID 下的本机进程可连接，这是预期的客户端边界；Named Pipe 不用于同一用户进程之间的隔离。
- 不创建 TCP listener，也不加入运行依赖。

## 验收与边界

- 多个本机客户端可以同时连接同一 host，响应保留各自请求 ID。
- 通过管道转换 `samples/demo.md`，输出字节与 `samples/demo.html` 一致。
- Backend idle shutdown 会停止 accept，并取消无数据客户端的阻塞读取；服务退出后无法建立新连接。
- Named Pipe host、IPC 客户端 API、session 单实例 ownership 与 GUI 客户端接入已建立；VS Code 接入和崩溃恢复仍在后续阶段。
- 客户端连接建立有超时；渲染请求/响应期限与 Node 自动重建策略属于 G9。
