# G6：Backend 单实例 ownership

## Ownership

`python -m backend serve` 在构造 Backend 或打开 Named Pipe 前，必须先取得当前 Windows 登录会话的
`Local\MarkdownReader.Backend.v1` named mutex。Mutex 使用与 Named Pipe 相同的 protected DACL：当前 logon SID 和
`LocalSystem`。owner 持有 mutex 直到 G5 host 返回；因此正常 idle shutdown 会先关闭 Node、停止 Pipe host，最后才释放
ownership。

竞争启动者不会构造 `Backend`，也不会启动 RendererSession。它反复尝试连接现有 Pipe 并请求 `status`，等待最长 15 秒；
就绪后回显现有服务的结构化状态并退出。如果原 owner 在等待期间退出，竞争者可取得已释放或 abandoned 的 mutex，
再成为唯一 owner。启动期限内既未连接到服务、也未取得 mutex 时，返回 `backend_start_timeout`，不会绕过仲裁创建第二个 host。

Mutex 是 per-session，而不是机器全局互斥；这与 Pipe 的 `LOCAL` 命名及 logon SID 安全边界一致。GUI 和 VS Code 之后应
通过同一启动入口确保服务，再连接 Named Pipe；它们的客户端迁移仍属于 G7/G8。

## 验收

- 两个不同进程竞争同一个 mutex 时只有一个能成为 owner。
- 原 owner 异常退出后，等待者可从 abandoned mutex 接管。
- owner 正在创建服务期间启动的第二个入口会等待 Pipe ready，然后返回同一个 Backend PID。
- 通过共享 Backend 转换 demo 后，竞争启动者看到的 Renderer PID 与现有 Backend 状态一致。
- 进程崩溃后遗留 renderer 子进程的恢复不由 mutex 本身解决，属于 G9 故障恢复范围。
