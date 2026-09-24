"use strict";

/**
 * MarkdownReader renderer build（esbuild）。
 *
 * 输入：renderer/entry.js 及其静态引用（含 pinned 上游两个扩展）+ renderer/node_modules
 * 输出：<repoRoot>/renderer/dist/renderer.cjs —— 单个 CJS 文件，**不入库**（npm run build 重现）
 *
 * 为什么需要 bundler：上游扩展文件位于 upstream/vscode-office/…，它自己的 require("katex")
 * 会从该目录向上查找 node_modules，而那里既没有也不允许安装。因此在构建期一次性把
 * 「上游源码 + renderer 自己的依赖 + adapter」打成单文件，并用 nodePaths 明确指向
 * renderer/node_modules：这是仓库内唯一、可提交、可复现的解析规则。
 * 明确不用：全局 NODE_PATH、junction、上游内 npm install、修改或复制上游文件。
 *
 * provenance gate：构建前必须验证 pin manifest == authoritative gitlink == upstream checkout HEAD
 * 三者一致；否则拒绝构建（不写 dist、不谎报来源）。检查只读，不修改任何 Git 状态。
 *
 * 参数：
 *   --check-provenance   只跑 provenance 校验并输出 JSON（不需要 node_modules）
 *   --repo-root <path>   覆盖仓库根（默认本文件所在仓库）；主要供测试注入 fixture
 */

const path = require("path");
const paths = require("../upstream/paths.js");

const RENDERER_ROOT = path.resolve(__dirname, "..");

function parseArgs(argv) {
  const options = { checkOnly: false, repoRoot: "" };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--check-provenance") {
      options.checkOnly = true;
    } else if (argv[index] === "--repo-root") {
      options.repoRoot = argv[index + 1] || "";
      index += 1;
    }
  }
  return options;
}

function reportFailure(provenance) {
  process.stderr.write(
    "[renderer] 拒绝构建：upstream provenance 校验失败（继续构建会打包未 pin 的源码）。\n" +
      provenance.problems.map(function (item) {
        return "  - " + item;
      }).join("\n") +
      "\n  pinned_commit   = " + (provenance.pinned_commit || "(未知)") +
      "\n  gitlink_commit  = " + (provenance.gitlink_commit || "(未知)") +
      "\n  checkout_commit = " + (provenance.checkout_commit || "(未知)") +
      "\n  " + provenance.guidance + "\n",
  );
  process.exitCode = 1;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const layout = paths.resolveLayout(options.repoRoot);
  const provenance = paths.checkProvenance({ repoRoot: options.repoRoot });
  const outFile = path.join(layout.repoRoot, "renderer", "dist", "renderer.cjs");

  if (!provenance.ok) {
    reportFailure(provenance);
    return;
  }

  if (options.checkOnly) {
    process.stdout.write(
      JSON.stringify({
        ok: true,
        repo_root: provenance.repo_root,
        pinned_commit: provenance.pinned_commit,
        gitlink_commit: provenance.gitlink_commit,
        checkout_commit: provenance.checkout_commit,
        output_file: outFile,
      }) + "\n",
    );
    return;
  }

  const missing = paths.missingSources(layout);
  if (missing.length > 0) {
    process.stderr.write(
      "[renderer] 缺少 pinned 上游源文件：" + missing.join("、") +
        "\n请先初始化 submodule：git submodule update --init --recursive\n",
    );
    process.exitCode = 1;
    return;
  }

  // esbuild 只在真正打包时加载：--check-provenance 不需要 node_modules。
  const esbuild = require("esbuild");
  const result = await esbuild.build({
    entryPoints: [path.join(RENDERER_ROOT, "entry.js")],
    outfile: outFile,
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
    "[renderer] built " + path.relative(layout.repoRoot, outFile).replace(/\\/g, "/") +
      " (" + bytes + " bytes) from " + paths.REUSED_SOURCES.length + " pinned upstream source(s)\n" +
      "[renderer] pinned_commit = " + provenance.pinned_commit +
      "  checkout_commit = " + provenance.checkout_commit + "  (verified equal)\n",
  );
}

main().catch(function (error) {
  process.stderr.write(
    "[renderer] build failed: " + (error && error.message ? error.message : String(error)) + "\n",
  );
  process.exitCode = 1;
});
