# vendored Mermaid runtime

这里放的是 **MarkdownReader 发行时使用的 Mermaid 浏览器 runtime**，与 `renderer/node_modules` 无关：
普通 `npm run build` 只读它、校验它、复制到 `renderer/dist/mermaid/`，**绝不联网、绝不更新**。

## 内容

```text
mermaid/<version>/
├─ mermaid.min.js     ← 与 npm 包内 dist/mermaid.min.js **逐字节相同**（不做任何本地修改）
├─ LICENSE            ← 上游 MIT 许可证原文
└─ metadata.json      ← 版本 / 来源 / tarball sha1 / 产物 sha256 / 字节数 / 取回日期
```

`mermaid.min.js` 是上游发布的 UMD（esbuild）构建：自包含、无动态 `import`，因此离线打开生成的 HTML
也能渲染；这也是**不**把 `mermaid` 加进 `renderer/package.json` 依赖的原因（那会把它的依赖树带进
bundle：实测 1.06 MB → 7.17 MB / 1929 modules）。

## 为什么 vendored 而不是构建期下载

- 最终 HTML 需要的是**浏览器 runtime**，不是 Node 侧 API；它是产品资产，不是构建工具；
- 普通 build 必须离线可重复：`npm ci` → `npm run build` 不应依赖网络；
- 升级要有审计链：版本、来源与产物哈希都进 metadata，并由 build 校验。

`metadata.json` 里的版本必须与 pinned 上游 `upstream/vscode-office/package.json` 声明的
`mermaid` 范围一致（当前 `^11.15.0`，因此这里 pin `11.15.0`）。

## 升级

```powershell
# 唯一会联网的入口；只在主动升级 runtime 时运行
pwsh tools/update_mermaid_runtime.ps1 -Version 11.15.0
pwsh tools/update_mermaid_runtime.ps1 -Version 11.16.0 -ExpectSha256 <期望的 sha256>
```

脚本用 `npm pack mermaid@<version>` 取精确版本，只提取 `dist/mermaid.min.js` 与 `LICENSE`
（sourcemap、ESM、`.d.ts` 刻意不带进仓库），写入新的 `<version>/` 目录并更新 metadata。
提交时请在 commit message 里写清 from → to 与新的 sha256。

## 校验（build gate）

`renderer/build/build.js` 在**任何写入之前**校验：版本目录唯一、`metadata.json` 可读、
产物与许可证存在、`metadata.version` == 目录名、`artifact_sha256` == 实测 SHA-256、
`artifact_bytes` == 实测字节数。任一不符即拒绝构建（只验证、不修复、不下载）。
产物全部先写进 `dist/.staging/`，复验通过后才替换 `dist/` 里受管的 `renderer.cjs` / `katex/` / `mermaid/`，
因此失败的构建不会留下「看起来可用、实际不同步」的 runtime set。

运行期 `renderer/resources/mermaid_runtime.js` 会再校验一次 SHA-256，被改动过的 runtime 不会交付。
