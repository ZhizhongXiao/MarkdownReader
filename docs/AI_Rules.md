# 维护约定

给在本仓库工作的自动化助手与未来的自己：这里是容易踩的约定，不是教程。
功能与操作见 [使用说明](USAGE.md)，环境与流程见 [开发与构建](DEVELOPMENT.md)。

## 当前版本

1.0.0-rc1，实机验收已通过；升为 1.0.0 待许可证与正式发布决定。

## 改动之后必须做的

- 改模板或渲染输出：运行 `python tools/generate_demo.py` 并提交重新生成的 `samples/demo.html`
  ——测试会比较它与当前源码的结果，不一致就是失败。
- 改 `viewer/`、`themes/`、`templates/`、`node_renderer/`、`core/`、`gui/`：至少运行 `python -m pytest -q`。
- 改 GUI：确认 `python main.py` 能启动，GUI 资源路径没有被破坏。
- 改打包配置：确认内置 Node 仍在，并运行 `python packaging/validate_release.py --mode both`。

## 不要做

- 不要在文档里写测试总数或契约条数：它们会随测试变化；真值由测试里的锁定常量与失败信息给出。
- 不要把当前态文档当历史：`docs/CHANGELOG.md`、`docs/QA-CHECKLIST.md` 与 `release-readme.md` 是冻结证据，
  不要为了描述现状去改它们。
- 不要在 `samples/demo.md` 里解释「以前为什么这样」，也不要写尚未支持的语法：它是渲染标本。
- 不要复制阅读器交互：交互只在 `viewer/js/`（装配时按 `manifest.json` 拼成一个脚本），主题只覆盖视觉。
- 不要引用 CDN、外链字体或在线资源：生成的 HTML 必须离线自足。

## 出口

- 模板或渲染有改动：Demo 重新生成并一起提交。
- 行为契约有改动：同步契约与实现，不要只改一侧让测试变绿。
- 版本与发布：先 `python packaging/release_freeze.py --check-only`，通过后再 `--tag`。
