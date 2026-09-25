"use strict";

/**
 * 资源收集（Phase 5A 建立，Phase 5C 扩到远程资源）：parse 之后、render 之前处理「需要资源层的引用」。
 *
 * 边界（沿用 K13，不得扩大）：
 *   - **只处理 Markdown 语义 token**：image token 与插件的 uml_diagram token。raw HTML
 *     （html_inline / html_block）里的图片与 style 里的 url(...) 保持原样，绝不扫描 HTML；
 *   - 所有 image token **先 classify**：data: / 其它 scheme / remote 都不需要 source_path；
 *     只有 local 需要 source_path 才解析；没有基准时保留引用（kept 且不报 warning ——
 *     缺少解析上下文不等于文件错误，也不引入 unresolved 状态）；
 *   - 远程（Phase 5C）：联网成功 → data URI；失败 → 保留作者原引用 + 可读 warning + 转换继续
 *     （`options.fetch_remote_resources = false` 时明确不抓取：kept 且不报 warning）。
 *
 * 顺序：jobs 按文档顺序建立，结果按 index 写回 → manifest / warnings / HTML mutation 均为文档顺序，
 * 与并发完成顺序无关（并发上限见 remote_resolver.js::MAX_CONCURRENCY）。
 *
 * KaTeX（K21）：只有出现数学 token 时才把样式（字体已内嵌）放进 resources.styles。
 * Mermaid（5B/AGENTS §9）：只有文档真的含 Mermaid 时才把 vendored runtime 放进 resources.scripts。
 *   识别复用 4C 的唯一 predicate（extensions/mermaid_export.js::isMermaidFence）；不能用 token.meta
 *   标记，因为那个标记是 fence **renderer** 在 render 阶段写上的，而 collector 跑在 render 之前。
 */

const path = require("path");
const { isMermaidFence } = require("../extensions/mermaid_export");
const { createLocalFileReader } = require("./local_file");
const { createHttpClient } = require("./http_client");
const { loadKatexStyle } = require("./katex_assets");
const { loadMermaidRuntime } = require("./mermaid_runtime");
const {
  MAX_CONCURRENCY,
  normalizeRemoteUrl,
  toDataUri,
  remoteFailureWarning,
  createRemoteResolver,
  runWithConcurrency,
} = require("./remote_resolver");

const IMAGE_KIND = "image";
const PLANTUML_KIND = "plantuml";
const MATH_TOKEN_TYPES = ["math_inline", "math_block"];
const MISSING_IMAGE_WARNING = "图片无法内嵌，保留原引用：";

// Windows 绝对路径（C:/dir/a.png）必须先判：否则会被通用 scheme 规则误判成 other-scheme。
// 顺序与旧 production renderer 的 resolveImageSource 一致。
const ABSOLUTE_WINDOWS = /^[a-zA-Z]:[\\/]/;

function classifySource(reference) {
  const raw = String(reference === undefined || reference === null ? "" : reference);
  if (/^data:/i.test(raw)) {
    return "data";
  }
  if (/^(https?:)?\/\//i.test(raw)) {
    return "remote";
  }
  if (ABSOLUTE_WINDOWS.test(raw)) {
    return "local";
  }
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(raw)) {
    return "other-scheme";
  }
  return "local";
}

function walkTokens(tokens, visit) {
  for (const token of tokens || []) {
    visit(token);
    if (token.children && token.children.length) {
      walkTokens(token.children, visit);
    }
  }
}

// 每个需要资源层的语义 token → 一个 job。job.index 即文档顺序，最终按它写回 token/manifest/warnings。
function collectJobs(tokens) {
  const jobs = [];
  walkTokens(tokens, function (token) {
    if (token.type !== "image" && token.type !== "uml_diagram") {
      return;
    }
    for (const attribute of token.attrs || []) {
      if (attribute[0] !== "src") {
        continue;
      }
      const reference = String(attribute[1] === undefined || attribute[1] === null ? "" : attribute[1]);
      jobs.push({
        index: jobs.length,
        kind: token.type === "uml_diagram" ? PLANTUML_KIND : IMAGE_KIND,
        attr: attribute,
        reference: reference,
        source: classifySource(reference),
      });
    }
  });
  return jobs;
}

// 选项只过滤「非数字」；有效范围（正数 / 非负整数）由 http_client 的 policy gate 单点判定，
// 越界值在这里原样传下去并最终回落默认值 —— 本层不重复实现 gate，避免两处规则不一致。
function optionNumber(value) {
  return Number.isFinite(value) ? Number(value) : undefined;
}

// 非远程的 job 同步结算：local 需要 source_path，其余（data: / 其它 scheme）一律 kept。
// fetchEnabled=false 时 remote 也在这里结算成 kept（明确关闭抓取，不是失败）。
function settleLocalAndKeptJobs(jobs, baseDirectory, reader, fetchEnabled) {
  const remote = [];
  for (const job of jobs) {
    if (job.source === "remote") {
      const fetchUrl = normalizeRemoteUrl(job.reference);
      if (!fetchEnabled || !fetchUrl) {
        job.outcome = { status: "kept" };
      } else {
        job.fetchUrl = fetchUrl;
        remote.push(job);
      }
      continue;
    }
    if (job.source !== "local") {
      job.outcome = { status: "kept" };
      continue;
    }
    if (!baseDirectory) {
      // 没有 source_path 就没有解析基准：保留引用、不报 warning、不算 failed。
      job.outcome = { status: "kept" };
      continue;
    }
    const localWarnings = [];
    const file = reader.read(job.reference, baseDirectory, localWarnings, MISSING_IMAGE_WARNING);
    job.outcome = file
      ? {
          status: "inlined",
          dataUri: file.dataUri,
          mimeType: file.mimeType,
          resolved: file.absolute,
        }
      : {
          status: "failed",
          warning: localWarnings.length > 0 ? localWarnings[0] : MISSING_IMAGE_WARNING + job.reference,
        };
  }
  return remote;
}

// 按文档顺序把结果落到 token / manifest / warnings。同一远程 URL 的同一失败只产生一条 warning。
function applyJobOutcomes(jobs, items, warnings) {
  const warnedUrls = new Set();
  for (const job of jobs) {
    const outcome = job.outcome;
    if (!outcome) {
      continue;
    }
    if (outcome.status === "inlined") {
      job.attr[1] = outcome.dataUri;
      items.push({
        kind: job.kind,
        source: job.source,
        ref: job.reference,
        status: "inlined",
        mime: outcome.mimeType,
        resolved: outcome.resolved,
      });
      continue;
    }
    if (outcome.status === "failed") {
      items.push({ kind: job.kind, source: job.source, ref: job.reference, status: "failed" });
      if (outcome.warning) {
        warnings.push(outcome.warning);
      } else {
        const key = job.fetchUrl || job.reference;
        if (!warnedUrls.has(key)) {
          warnedUrls.add(key);
          warnings.push(remoteFailureWarning(job.reference, outcome.reason));
        }
      }
      continue;
    }
    items.push({ kind: job.kind, source: job.source, ref: job.reference, status: "kept" });
  }
}

async function collectResources(tokens, context, options) {
  const items = [];
  const styles = [];
  const scripts = [];
  const warnings = [];
  const settings = context || {};
  const rendererOptions = options || {};
  const sourcePath = settings.source_path || "";
  const reader = createLocalFileReader();
  const baseDirectory = sourcePath ? path.dirname(sourcePath) : "";
  // 明确关闭抓取（测试默认 / 离线转换）：remote 只 kept，不联网、也不报 warning。
  const fetchEnabled = rendererOptions.fetch_remote_resources !== false;
  let hasMathTokens = false;
  let hasMermaidFence = false;

  walkTokens(tokens, function (token) {
    if (MATH_TOKEN_TYPES.indexOf(token.type) >= 0) {
      hasMathTokens = true;
    }
    if (token.type === "fence" && isMermaidFence(token.info, token.content)) {
      hasMermaidFence = true;
    }
  });

  // 资源层（5A/5C）：先按文档顺序建 job → 并发抓取 → 再按文档顺序写回。
  const jobs = collectJobs(tokens);
  const remoteJobs = settleLocalAndKeptJobs(jobs, baseDirectory, reader, fetchEnabled);
  if (fetchEnabled && remoteJobs.length > 0) {
    const client = createHttpClient({
      timeoutMs: optionNumber(rendererOptions.resource_timeout_ms),
      retries: optionNumber(rendererOptions.resource_retries),
      maxBytes: optionNumber(rendererOptions.resource_max_bytes),
    });
    const resolver = createRemoteResolver({ client: client });
    await runWithConcurrency(remoteJobs, MAX_CONCURRENCY, async function (job) {
      const result = await resolver.resolve(job.fetchUrl);
      job.outcome = result.ok
        ? {
            status: "inlined",
            dataUri: toDataUri(result),
            mimeType: result.mimeType,
            resolved: result.finalUrl,
          }
        : { status: "failed", reason: result.reason };
    });
  }
  applyJobOutcomes(jobs, items, warnings);

  // KaTeX 载荷只取决于数学 token（K21），与源文件上下文无关。
  if (hasMathTokens) {
    const style = loadKatexStyle(reader, warnings);
    if (style) {
      styles.push({ id: style.id, css: style.css });
      for (const item of style.items) {
        items.push(item);
      }
    }
  }

  // Mermaid 载荷只取决于 fence 识别（AGENTS §9），与源文件上下文无关。
  if (hasMermaidFence) {
    const runtime = loadMermaidRuntime(warnings);
    if (runtime) {
      scripts.push({
        id: runtime.id,
        version: runtime.version,
        script: runtime.script,
        boot: runtime.boot,
      });
      items.push(runtime.item);
    }
  }

  return { items: items, styles: styles, scripts: scripts, warnings: warnings };
}

module.exports = {
  collectResources: collectResources,
  IMAGE_KIND: IMAGE_KIND,
  MISSING_IMAGE_WARNING: MISSING_IMAGE_WARNING,
};
