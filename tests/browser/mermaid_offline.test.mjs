"use strict";

/**
 * Mermaid 离线渲染验收（Phase 5B，opt-in）。
 *
 * 默认 pytest 不依赖浏览器；本套件由 `pwsh tools/run_browser_acceptance.ps1` 显式触发。
 * 它证明的是 roadmap 的验收：「包含 Mermaid 的 HTML 离线打开后仍可正常显示」：
 *   1) 用真实 adapter 渲染文档（拿到 html + resources.scripts）；
 *   2) 自己装配页面（模拟未来 assembler：注入 runtime 与 boot）；
 *   3) 拦截并记录所有非 file:// 请求（必须为 0）；
 *   4) 断言 .mermaid 容器里真的生成了 <svg>。
 *
 * 浏览器默认用系统已装的 Edge（channel: msedge），不下载浏览器；
 * 可用 MR_BROWSER_CHANNEL=chrome|chromium 覆盖。
 */

import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, "..", "..");
const ARTIFACT = path.join(REPO_ROOT, "renderer", "dist", "renderer.cjs");
const CHANNEL = process.env.MR_BROWSER_CHANNEL || "msedge";
const DIAGRAMS = [
  "graph LR\n  A[开始] --> B{判断}\n  B -->|是| C[结束]\n  B -->|否| A",
  "sequenceDiagram\n  Alice->>Bob: 你好\n  Bob-->>Alice: 再见",
  "gantt\n  title 计划\n  dateFormat YYYY-MM-DD\n  section 阶段\n  设计 :a1, 2026-01-01, 5d",
];

let browser = null;
let playwright = null;

function requireArtifact() {
  assert.ok(
    fs.existsSync(ARTIFACT),
    "缺少 renderer/dist/renderer.cjs：先执行 cd renderer; npm ci; npm run build",
  );
}

function renderWithAdapter(markdown) {
  requireArtifact();
  const completed = spawnSync(process.execPath, [ARTIFACT], {
    input: JSON.stringify({ markdown, options: {}, context: {} }),
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  assert.equal(completed.status, 0, completed.stderr);
  return JSON.parse(completed.stdout);
}

/** 模拟未来 assembler 的装配：容器 HTML + runtime + boot，全部内联（无外链）。 */
function assemblePage(envelope, options) {
  const scripts = envelope.resources.scripts;
  const injected = (options && options.withRuntime) === false ? [] : scripts;
  const tags = injected
    .map((entry) => "<script>\n" + entry.script + "\n</script>\n<script>\n" + entry.boot + "\n</script>")
    .join("\n");

  return [
    "<!doctype html>",
    '<html lang="zh"><head><meta charset="utf-8"><title>mermaid offline acceptance</title></head>',
    "<body>",
    envelope.html,
    tags,
    "</body></html>",
  ].join("\n");
}

function writePage(directory, name, content) {
  const file = path.join(directory, name);
  fs.writeFileSync(file, content, "utf8");
  return "file:///" + file.replace(/\\/g, "/");
}

async function openPage(url, blocked) {
  const page = await browser.newPage();
  await page.route("**/*", (route) => {
    const target = route.request().url();
    if (target.startsWith("file://")) {
      return route.continue();
    }
    blocked.push(target);
    return route.abort();
  });
  await page.goto(url);
  return page;
}

before(async () => {
  requireArtifact();
  try {
    playwright = await import("playwright");
  } catch (error) {
    assert.fail(
      "缺少 playwright（opt-in 依赖）：先执行 cd tests/browser; npm ci —— " + error.message,
    );
  }
  try {
    browser = await playwright.chromium.launch({ channel: CHANNEL });
  } catch (error) {
    assert.fail(
      "无法启动浏览器 channel=" + CHANNEL + "：" + error.message +
        "\n可用 MR_BROWSER_CHANNEL=chrome，或 npx playwright install chromium 后设成 chromium。",
    );
  }
});

after(async () => {
  if (browser) {
    await browser.close();
  }
});

test("the container round-trips the author source before any runtime runs", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "mr-browser-"));
  const source = "graph TD\n  A[\"a &amp; b\"] --> B";
  const envelope = renderWithAdapter("```mermaid\n" + source + "\n```\n");
  const url = writePage(directory, "roundtrip.html", assemblePage(envelope, { withRuntime: false }));
  const blocked = [];

  const page = await openPage(url, blocked);
  const text = await page.locator("div.mermaid").first().textContent();

  assert.equal(text, source, "Phase 4C 的 D2 不变式：DOM 文本必须等于作者原文");
  assert.deepEqual(blocked, [], "静态页面不得发起任何网络请求");
  await page.close();
});

for (const [index, diagram] of DIAGRAMS.entries()) {
  test("diagram " + (index + 1) + " renders an inline SVG with the network blocked", async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "mr-browser-"));
    const envelope = renderWithAdapter("```mermaid\n" + diagram + "\n```\n");
    assert.equal(envelope.resources.scripts.length, 1, "Mermaid 文档必须交付 runtime");
    const url = writePage(directory, "diagram-" + index + ".html", assemblePage(envelope));
    const blocked = [];

    const page = await openPage(url, blocked);
    const svg = page.locator("div.mermaid svg").first();
    await svg.waitFor({ state: "attached", timeout: 30_000 });

    assert.ok((await svg.count()) >= 1, "runtime 必须真的产出 SVG");
    assert.deepEqual(blocked, [], "离线渲染不得访问网络（CDN / icon pack / 字体）");
    assert.equal(await page.locator("body").getAttribute("data-mermaid-error"), null);
    await page.close();
  });
}
