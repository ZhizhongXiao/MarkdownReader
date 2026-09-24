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
 * 资产发布是事务式的（Phase 5B）：renderer.cjs、katex/、mermaid/ 全部先写进 dist/.staging 并复验
 * （含 vendored Mermaid runtime 的 SHA-256），只有全部成功才替换 dist 里已受管的同名内容。
 * 任何失败都发生在替换之前，因此不会留下「看起来可用、实际不同步」的 runtime set。
 * vendored Mermaid runtime 的来源校验同样是 gate：metadata 与产物不一致就拒绝构建（只验证、不下载）。
 *
 * 参数：
 *   --check-provenance   只跑 provenance 校验并输出 JSON（不需要 node_modules）
 *   --repo-root <path>   覆盖仓库根（默认本文件所在仓库）；主要供测试注入 fixture
 */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { extractCssReferences } = require("../resources/css_resolver");
const paths = require("../upstream/paths.js");

const RENDERER_ROOT = path.resolve(__dirname, "..");
const BUNDLE_NAME = "renderer.cjs";
const KATEX_DIRECTORY = "katex";
const MERMAID_DIRECTORY = "mermaid";
const STAGING_DIRECTORY = ".staging";
// dist 里由 build 全权管理的名字：替换时只清这些，不碰别的东西。
const MANAGED_ASSETS = [BUNDLE_NAME, KATEX_DIRECTORY, MERMAID_DIRECTORY];

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

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

// Phase 5B：vendored Mermaid runtime 的来源校验。只读、不联网、不写 dist。
// 与 Phase 2 的 upstream provenance 同一思路：来源与产物都必须可核对，缺失或被改动一律拒绝构建。
function verifyVendoredMermaid(repoRoot) {
  const vendorRoot = path.join(repoRoot, "renderer", "vendor", "mermaid");
  if (!fs.existsSync(vendorRoot)) {
    return { ok: false, problems: ["缺少 vendored Mermaid runtime 目录：renderer/vendor/mermaid"] };
  }
  const versions = fs.readdirSync(vendorRoot).filter(function (name) {
    return fs.existsSync(path.join(vendorRoot, name, "metadata.json"));
  });
  if (versions.length !== 1) {
    return {
      ok: false,
      problems: [
        "renderer/vendor/mermaid 必须恰好有一个带 metadata.json 的版本目录，实际 " + versions.length + " 个",
      ],
    };
  }

  const version = versions[0];
  const directory = path.join(vendorRoot, version);
  const artifactPath = path.join(directory, "mermaid.min.js");
  const licensePath = path.join(directory, "LICENSE");
  const problems = [];
  let metadata = null;
  try {
    metadata = JSON.parse(fs.readFileSync(path.join(directory, "metadata.json"), "utf8"));
  } catch (error) {
    problems.push("vendor metadata.json 不可读：" + error.message);
  }
  if (!fs.existsSync(artifactPath)) {
    problems.push("缺少 runtime 产物：renderer/vendor/mermaid/" + version + "/mermaid.min.js");
  }
  if (!fs.existsSync(licensePath)) {
    problems.push("缺少许可证：renderer/vendor/mermaid/" + version + "/LICENSE");
  }

  let actual = "";
  if (problems.length === 0) {
    actual = sha256File(artifactPath);
    const bytes = fs.statSync(artifactPath).size;
    if (String(metadata.version || "") !== version) {
      problems.push("metadata.version(" + metadata.version + ") 与目录名(" + version + ") 不一致");
    }
    if (String(metadata.artifact_sha256 || "") !== actual) {
      problems.push(
        "runtime SHA-256 与 metadata 不一致：metadata " + metadata.artifact_sha256 + " / actual " + actual,
      );
    }
    if (Number(metadata.artifact_bytes) !== bytes) {
      problems.push("runtime 字节数与 metadata 不一致：" + metadata.artifact_bytes + " / " + bytes);
    }
  }

  return {
    ok: problems.length === 0,
    version: version,
    directory: directory,
    artifactPath: artifactPath,
    licensePath: licensePath,
    metadata: metadata,
    sha256: actual,
    problems: problems,
  };
}

// KaTeX 样式与它**真正引用**的字体：清单由 CSS 驱动，不无脑复制整个 npm dist。
function copyKatexAssets(sourceDirectory, targetDirectory) {
  const css = fs.readFileSync(path.join(sourceDirectory, "katex.min.css"), "utf8");
  fs.mkdirSync(targetDirectory, { recursive: true });
  fs.writeFileSync(path.join(targetDirectory, "katex.min.css"), css);
  let files = 1;
  let bytes = Buffer.byteLength(css);
  for (const reference of extractCssReferences(css)) {
    const source = path.join(sourceDirectory, reference);
    const target = path.join(targetDirectory, reference);
    const content = fs.readFileSync(source);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, content);
    files += 1;
    bytes += content.length;
  }
  return { files: files, bytes: bytes };
}

// vendor 里的产物 + metadata + 许可证一起发布：运行期还要用 metadata 复验 SHA-256。
function copyMermaidRuntime(vendor, targetDirectory) {
  fs.mkdirSync(targetDirectory, { recursive: true });
  fs.copyFileSync(vendor.artifactPath, path.join(targetDirectory, "mermaid.min.js"));
  fs.copyFileSync(path.join(vendor.directory, "metadata.json"), path.join(targetDirectory, "metadata.json"));
  fs.copyFileSync(vendor.licensePath, path.join(targetDirectory, "LICENSE"));
}

// 事务式资产发布：全部产物先写进 dist/.staging 并复验，只有全部成功才替换正式内容。
function prepareStaging(distDirectory) {
  const staging = path.join(distDirectory, STAGING_DIRECTORY);
  fs.rmSync(staging, { recursive: true, force: true });
  fs.mkdirSync(staging, { recursive: true });
  return staging;
}

function verifyStaging(staging, vendor) {
  const problems = [];
  const expected = [
    path.join(staging, BUNDLE_NAME),
    path.join(staging, KATEX_DIRECTORY, "katex.min.css"),
    path.join(staging, KATEX_DIRECTORY, "fonts", "KaTeX_Main-Regular.woff2"),
    path.join(staging, MERMAID_DIRECTORY, "mermaid.min.js"),
    path.join(staging, MERMAID_DIRECTORY, "metadata.json"),
  ];
  for (const target of expected) {
    if (!fs.existsSync(target)) {
      problems.push("staging 缺少文件：" + target);
    }
  }
  if (problems.length === 0) {
    const staged = sha256File(path.join(staging, MERMAID_DIRECTORY, "mermaid.min.js"));
    if (staged !== vendor.sha256) {
      problems.push("staging 里的 runtime 与 vendored 产物不一致（SHA-256 不同）");
    }
  }
  return problems;
}

// 只清 build 自己管理的名字，然后逐个搬进 dist；staging 目录本身最后删除。
function replaceManagedAssets(distDirectory, staging) {
  for (const name of MANAGED_ASSETS) {
    fs.rmSync(path.join(distDirectory, name), { recursive: true, force: true });
  }
  for (const name of fs.readdirSync(staging)) {
    fs.renameSync(path.join(staging, name), path.join(distDirectory, name));
  }
  fs.rmSync(staging, { recursive: true, force: true });
}

function reportVendorFailure(vendor) {
  process.stderr.write(
    "[renderer] 拒绝构建：vendored Mermaid runtime 校验失败" +
      "（继续构建会打包与 metadata 不一致的 runtime）。\n" +
      vendor.problems.map(function (item) {
        return "  - " + item;
      }).join("\n") +
      "\n  有意更新 runtime 时：pwsh tools/update_mermaid_runtime.ps1 -Version <version>\n" +
      "  本检查只验证、不修复：不会联网下载，也不会改写 renderer/vendor。\n",
  );
  process.exitCode = 1;
}

function reportFailure(provenance) {
  process.stderr.write(
    "[renderer] 拒绝构建：upstream provenance 校验失败" +
      "（继续构建会打包与 pin 不一致或已被本地修改的源码）。\n" +
      provenance.problems.map(function (item) {
        return "  - " + item;
      }).join("\n") +
      "\n  pinned_commit   = " + (provenance.pinned_commit || "(未知)") +
      "\n  gitlink_commit  = " + (provenance.gitlink_commit || "(未知)") +
      "\n  checkout_commit = " + (provenance.checkout_commit || "(未知)") +
      "\n  worktree_clean  = " + (provenance.worktree_clean ? "true" : "false") +
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
        worktree_clean: provenance.worktree_clean,
        worktree_changes: provenance.worktree_changes,
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

  // Phase 5B：资产校验先于任何写入 —— 校验失败时 dist 完全不被触碰。
  const vendor = verifyVendoredMermaid(layout.repoRoot);
  if (!vendor.ok) {
    reportVendorFailure(vendor);
    return;
  }
  const katexSource = path.join(RENDERER_ROOT, "node_modules", "katex", "dist");
  if (!fs.existsSync(path.join(katexSource, "katex.min.css"))) {
    process.stderr.write(
      "[renderer] 拒绝构建：缺少 " + katexSource + "（先执行 cd renderer; npm ci）\n",
    );
    process.exitCode = 1;
    return;
  }

  const distDirectory = path.dirname(outFile);
  const staging = prepareStaging(distDirectory);
  const stagedBundle = path.join(staging, BUNDLE_NAME);

  // esbuild 只在真正打包时加载：--check-provenance 不需要 node_modules。
  const esbuild = require("esbuild");
  const result = await esbuild.build({
    entryPoints: [path.join(RENDERER_ROOT, "entry.js")],
    outfile: stagedBundle,
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

  // companion runtime set：KaTeX 样式与字体（CSS 驱动）+ vendored Mermaid runtime。
  const katexAssets = copyKatexAssets(katexSource, path.join(staging, KATEX_DIRECTORY));
  copyMermaidRuntime(vendor, path.join(staging, MERMAID_DIRECTORY));

  const stagedProblems = verifyStaging(staging, vendor);
  if (stagedProblems.length > 0) {
    process.stderr.write(
      "[renderer] 拒绝替换 dist：staging 校验失败\n" +
        stagedProblems.map(function (item) {
          return "  - " + item;
        }).join("\n") +
        "\n  dist 未被修改（旧 runtime set 保持可用）。\n",
    );
    process.exitCode = 1;
    return;
  }

  replaceManagedAssets(distDirectory, staging);

  const outputs = Object.keys(result.metafile.outputs);
  const bytes = outputs.length ? result.metafile.outputs[outputs[0]].bytes : 0;
  process.stdout.write(
    "[renderer] built " + path.relative(layout.repoRoot, outFile).replace(/\\/g, "/") +
      " (" + bytes + " bytes) from " + paths.REUSED_SOURCES.length + " pinned upstream source(s)\n" +
      "[renderer] assets: katex " + katexAssets.files + " file(s) / " + katexAssets.bytes + " bytes" +
      " + mermaid " + vendor.version + " (" + vendor.sha256.slice(0, 12) + "…, verified)\n" +
      "[renderer] dist replaced atomically from " + STAGING_DIRECTORY + "/ (staging verified first)\n" +
      "[renderer] pinned_commit = " + provenance.pinned_commit +
      "  checkout_commit = " + provenance.checkout_commit + "  (verified equal)\n",
  );
}

if (require.main === module) {
  main().catch(function (error) {
    process.stderr.write(
      "[renderer] build failed: " + (error && error.message ? error.message : String(error)) + "\n",
    );
    process.exitCode = 1;
  });
}

module.exports = {
  verifyVendoredMermaid: verifyVendoredMermaid,
  copyKatexAssets: copyKatexAssets,
  copyMermaidRuntime: copyMermaidRuntime,
  prepareStaging: prepareStaging,
  verifyStaging: verifyStaging,
  replaceManagedAssets: replaceManagedAssets,
  MANAGED_ASSETS: MANAGED_ASSETS,
};
