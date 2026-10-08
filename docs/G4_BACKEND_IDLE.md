# G4：Backend 空闲生命周期

## 行为

长寿命 `Backend` 创建时开始 120 秒空闲计时。每次合法的 `convert` 请求完成后，计时从完成时刻重新开始；
`status` 和无效请求不延长生命周期。当前 API 没有 preview 方法，后续若加入 preview，应按同一规则记录
实际渲染工作。

Backend 内部的 daemon watchdog 负责检测期限。期限到达后，它先拒绝新请求，再关闭并回收该 Backend 拥有的
`RendererSession`，最后触发 shutdown event。宿主主循环通过 `wait_for_shutdown()` 等待该 event；该方法仅在
Node 关闭后返回 `True`，宿主随后从主入口返回，操作系统即可回收 Backend 进程。显式 `close()` 走同一关闭
路径并唤醒等待者。

计时从 Backend 构造时开始，因此启动后没有任何转换请求的空闲宿主也会退出。单次 CLI 转换仍在命令完成时
立即关闭 Backend，不会延迟等待 120 秒。

## 并发和顺序

请求调度锁覆盖配置读取、core 转换和活动时间更新。watchdog 到期时会等待当前请求结束；如果请求在到期前
已经进入处理，它完成后会重设期限。watchdog 标记关闭后，后续请求返回 `backend_closed`。Node 关闭在
shutdown event 之前完成，宿主不会先退出而遗留 renderer 子进程。

G4 只管理 Backend 与 Node 的生命周期，不引入请求传输。G5 的 IPC host 需要在其主循环中等待同一
`wait_for_shutdown()` event，并在 event 触发后停止接受客户端、返回主入口。

## 验收

- 默认期限为 120 秒；测试用例使用短期限验证同一逻辑，不改变生产期限。
- 没有转换请求的长寿命 Backend 也会到期关闭。
- `status` 不刷新期限，完成的 `convert` 会刷新期限。
- 到期时 Node 子进程先退出，`wait_for_shutdown()` 才返回；Backend 拒绝后续请求。
- 显式 `close()` 会关闭 Node 并唤醒 shutdown waiter。
- 无 Named Pipe、TCP listener 或 GUI 依赖。
