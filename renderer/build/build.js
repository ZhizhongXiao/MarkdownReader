"use strict";

/**
 * MarkdownReader renderer build（esbuild）。
 *
 * 输入：renderer/entry.js 及其静态引用（含 pinned 上游两个扩展）+ renderer/node_modules
 * 输出：renderer/dist/renderer.cjs —— 单个 CJS 文件，**不入库**（用 npm run build 重现）
 *
 * 为什么需要 bundler：上游扩展文件位于 upstream/vscode-office/…，它自己的 require("katex")
 * 会从该目录向上查找 node_modules，而那里既没有也不允许安装。因此在构建期一次性把
 * 「上游源码 + renderer 自己的依赖 + adapter」打成单文件，并用 nodePaths 明确指向
 * renderer/node_modules：这是仓库内唯一、可提交、可复现的解析规则。
 *
 * 明确不用：全局 NODE_PATH、junction、上游内 npm install、修改或复制上游文件。
 */

const path = require("path");
const esbuild = require("esbuild");
const paths = require("../upstream/paths.js");

const RENDERER_ROOT = path.resolve(__dirname, "..");
const OUT_FILE = path.join(RENDERER_ROOT, "dist", "renderer.cjs");

async function main() {
  const missing = paths.missingSources();
  if (missing.length > 0) {
    process.stderr.write(
      "[renderer] 缺少 pinned 上游源文件：" + missing.join("、") +
        "\n请先初始化 submodule：git submodule update --init --recursive\n",
    );
    process.exitCode = 1;
    return;
  }

  const result = await esbuild.build({
    entryPoints: [path.join(RENDERER_ROOT, "entry.js")],
    outfile: OUT_FILE,
    bundle: true,
    platform: "node",
    format: "cjs",
    target: ["node18"],
    absWorkingDir: RENDERER_ROOT,
    nodePaths: [path.join(RENDERER_ROOT, "node_modules")],
    logLevel: "warning",
    metafile: true,
    banner: {
      js: "// 由 renderer/build/build.js 生成，请勿手工编辑。重建：cd renderer && npm run build",
    },
  });

  const outputs = Object.keys(result.metafile.outputs);
  const bytes = outputs.length ? result.metafile.outputs[outputs[0]].bytes : 0;
  process.stdout.write(
    "[renderer] built dist/renderer.cjs (" + bytes + " bytes) from " +
      paths.REUSED_SOURCES.length + " pinned upstream source(s) at " + paths.pinnedCommit() + "\n",
  );
}

main().catch(function (error) {
  process.stderr.write(
    "[renderer] build failed: " + (error && error.message ? error.message : String(error)) + "\n",
  );
  process.exitCode = 1;
});
