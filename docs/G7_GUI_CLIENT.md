# G7：GUI 客户端化

## 入口与生命周期

GUI 不导入 `core.converter` 的渲染入口，不再在窗口启动时校验 Node。首次需要状态或执行转换时，
`gui.services.backend_client.BackendClient` 先通过默认 Pipe 请求 `status`；连接失败时启动 headless Backend，
然后轮询 `status` 等待服务就绪。开发运行使用 `python -m backend serve`；冻结版由同一个 MarkdownReader EXE
通过 `--mdr-backend serve` 参数进入 Backend 分支。G6 mutex 处理多个 GUI/客户端同时启动的竞争。

Backend 是独立进程，GUI 关闭或断开不会终止它。最后一次实际转换后的 G4 120 秒 idle 计时仍由 Backend 管理；
单独的 `status` 不延长期限。冻结版 Backend 分支会关闭 PyInstaller splash，且不导入 GUI。

## 转换路径

GUI 保留文件选择、只读预检、输出路径计划和完成后打开文件；`core.batch` 继续负责批次调度、进度回调、metadata
收集与索引页生成。每篇 Markdown 单独发送版本化 `convert` 请求，Backend 在自己的 RendererSession 中渲染并完成
HTML assembly。批量转换连续复用同一 Backend/RendererSession；整批 `document_map` 随每篇请求传递，使
`.md → .html` 链接仍按转换计划重写。
内部默认主题 `modern` 与 overwrite、offline 等单篇选项由请求明确传入；外置主题、编号等持久配置仍由 Backend
从同一个 `config.json` 读取。

GUI 状态查询也经过 BackendClient 的 `status` 请求，可通过 `BridgeApi.get_backend_status()` 查询。Backend
失败以 GUI 转换结果/状态错误返回；G9 的 Node 崩溃自动重建、请求期限和重试不在本阶段实现。

设置页的主题安装管理仍在 GUI/Python core 中完成。现有主题预览是基于已验证 metadata 的静态示意，不执行用户 CSS，
也不需要 renderer；如果未来增加需要真实 Markdown renderer 的预览，则必须调用 Backend。

## 验收

- GUI Python 路径没有 `_DEFAULT_BRIDGE`、`core.converter.process_single/process_batch` 或 Node runtime preflight。
- GUI 先请求 status；服务缺失时启动 Backend 并等待 status；已有服务时不启动第二个 host。
- GUI 的单文件 demo 输出与 `samples/demo.html` 字节一致，默认 core bridge 没有 RendererSession。
- GUI 文件夹转换仍逐篇提交，跨文件链接映射、批次索引、进度状态和自动打开入口行为保留。
- 打包入口支持 headless Backend 参数，且不创建 pywebview 窗口。

VS Code 客户端、G9 崩溃恢复与 G10 性能验收仍属于后续阶段。
