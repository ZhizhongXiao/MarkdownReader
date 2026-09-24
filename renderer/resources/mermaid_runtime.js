"use strict";

/**
 * Mermaid browser runtime（Phase 5B）。
 *
 * 产物是 vendored 的**正式 browser 构建**（renderer/vendor/mermaid/<version>/mermaid.min.js：
 * 上游发布的 UMD/esbuild bundle，自包含、无动态 import），由 `npm run build` 复制到
 * dist/mermaid/。运行期只读 dist/mermaid/，**绝不联网**；普通 build 也不更新它
 * （更新只走 tools/update_mermaid_runtime.ps1）。
 *
 * 两层校验：
 *   - build：按 vendor metadata 的 SHA-256 校验后才会写进 dist（见 build/build.js）；
 *   - 运行期：这里再校验一次，被改动过的 runtime 不放行（warning + 不交付）。
 *
 * 载荷纪律（AGENTS §9）：只有文档真的含 Mermaid 时才交给 resources.scripts（由 collector 决定），
 * 普通 Markdown 的 envelope 与最终 HTML 都不背这几 MB。
 *
 * boot 与 runtime 同版本耦合，因此一起交付：Phase 6 的 Viewer 可以改样式，不应改这段 wiring。
 */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const RUNTIME_ID = "mermaid";
const ARTIFACT_NAME = "mermaid.min.js";
const METADATA_NAME = "metadata.json";

// mermaid 11：initialize **一次**，然后**每个容器各自** run。逐图隔离是本模块的契约：
// 单个图失败（parse error / 渲染异常）只影响它自己，不会阻止同页面其它合法图；
// 每个节点独立 catch，因此也不产生未捕获 rejection。
// 容器内容是 D2 escape 过的惰性文本，run 读取的 textContent 必须等于作者原文。
// 这里刻意不解析语法（Node 侧不调用 parse()），错误呈现交给 runtime 自身。
const BOOT = [
  "(function () {",
  "  function activate() {",
  '    if (!window.mermaid || typeof window.mermaid.run !== "function") { return; }',
  "    window.mermaid.initialize({ startOnLoad: false });",
  '    var nodes = Array.prototype.slice.call(document.querySelectorAll("div.mermaid"));',
  "    if (!nodes.length) { return; }",
  "    nodes.forEach(function (node) {",
  "      try {",
  "        Promise.resolve(window.mermaid.run({ nodes: [node] })).catch(function () { return undefined; });",
  "      } catch (error) {",
  "        return undefined;",
  "      }",
  "    });",
  "  }",
  '  if (document.readyState === "loading") {',
  '    document.addEventListener("DOMContentLoaded", activate);',
  "  } else {",
  "    activate();",
  "  }",
  "})();",
].join("\n");

// 资产目录解析规则必须同时支持两种布局（与 resources/katex_assets.js 同一模式）：
//   - 打包后：dist/renderer.cjs 与 dist/mermaid/ 同级；
//   - 源码布局：renderer/resources/*.js 对应 renderer/dist/mermaid/。
function resolveRuntimeDirectory() {
  const candidates = [
    path.join(__dirname, RUNTIME_ID),
    path.join(__dirname, "..", "dist", RUNTIME_ID),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(path.join(candidate, ARTIFACT_NAME))) {
      return candidate;
    }
  }
  return candidates[candidates.length - 1];
}

const RUNTIME_DIRECTORY = resolveRuntimeDirectory();

let cachedRuntime = null;

function resetMermaidRuntimeCache() {
  cachedRuntime = null;
}

function sha256(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

/** 读取并校验 vendored runtime；不可用或校验失败时返回 null 并写入 warning。 */
function loadMermaidRuntime(warnings) {
  if (cachedRuntime) {
    return cachedRuntime;
  }
  const artifactPath = path.join(RUNTIME_DIRECTORY, ARTIFACT_NAME);
  let bytes = null;
  let metadata = null;
  try {
    bytes = fs.readFileSync(artifactPath);
    metadata = JSON.parse(fs.readFileSync(path.join(RUNTIME_DIRECTORY, METADATA_NAME), "utf8"));
  } catch (error) {
    // 降级：runtime 缺失不阻断转换，但必须让用户看到（K15）。不缓存，后续转换仍会重试。
    warnings.push("Mermaid runtime 不可用（缺少构建产物 dist/mermaid/）：" + error.message);
    return null;
  }

  const actual = sha256(bytes);
  if (String(metadata.artifact_sha256 || "") !== actual) {
    warnings.push("Mermaid runtime 校验失败（SHA-256 与 metadata 不一致），本次不交付 runtime。");
    return null;
  }

  const version = String(metadata.version || "");
  cachedRuntime = {
    id: RUNTIME_ID,
    version: version,
    script: bytes.toString("utf8"),
    boot: BOOT,
    item: {
      kind: "runtime",
      source: "vendored",
      ref: RUNTIME_ID + "@" + version,
      status: "inlined",
      mime: "text/javascript",
      resolved: artifactPath,
    },
  };
  return cachedRuntime;
}

module.exports = {
  loadMermaidRuntime: loadMermaidRuntime,
  resetMermaidRuntimeCache: resetMermaidRuntimeCache,
  resolveRuntimeDirectory: resolveRuntimeDirectory,
  RUNTIME_DIRECTORY: RUNTIME_DIRECTORY,
  RUNTIME_ID: RUNTIME_ID,
  ARTIFACT_NAME: ARTIFACT_NAME,
  METADATA_NAME: METADATA_NAME,
  BOOT: BOOT,
};
