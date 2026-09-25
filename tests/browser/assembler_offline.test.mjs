"use strict";

/**
 * Python assembler 页面的离线 smoke（Phase 5D，opt-in）。
 *
 * 5B 证明的是「adapter envelope → JS 测试里的模拟装配 → Mermaid 离线可渲染」；
 * 这里证明的是另一条真实链：adapter envelope → **core/html_assembly.py** → 最终 HTML → 浏览器。
 * 后者才会暴露 `<script>` 注入位置、HTML 序列化、CSS 注入位置、runtime 与 boot 顺序、
 * 以及 assembler 漏掉某个 resources 通道这类问题。
 *
 * 页面来源（不传 MR_EXTRA_PAGE 时整条用例跳过）：
 *     uv run python tools/assemble_document.py --out build/smoke.html
 *     pwsh tools/run_browser_acceptance.ps1 -ExtraPage build/smoke.html
 *
 * 刻意不 import 5B spec 的 helper：5D 只加一条窄链，不去改 5B 的验收文件。
 */

import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import fs from "node:fs";
import path from "node:path";

const EXTRA_PAGE = process.env.MR_EXTRA_PAGE || "";
const CHANNEL = process.env.MR_BROWSER_CHANNEL || "msedge";

// 未捕获 rejection 必须在页面里就记下来：只断言「Mermaid 渲染成功」无法证明没有异常逃逸。
const REJECTION_HOOK =
  "window.__mrRejections = [];" +
  "window.addEventListener('unhandledrejection', function (event) {" +
  "  window.__mrRejections.push(String(event.reason && event.reason.message ? event.reason.message : event.reason));" +
  "});";

let browser = null;

before(async () => {
  if (!EXTRA_PAGE) {
    return;
  }
  assert.ok(fs.existsSync(EXTRA_PAGE), "MR_EXTRA_PAGE 指向的文件不存在：" + EXTRA_PAGE);
  let playwright = null;
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
    assert.fail("无法启动浏览器 channel=" + CHANNEL + "：" + error.message);
  }
});

after(async () => {
  if (browser) {
    await browser.close();
  }
});

test(
  "the Python-assembled page renders offline without any network request",
  {
    skip: EXTRA_PAGE
      ? false
      : "需要 MR_EXTRA_PAGE（pwsh tools/run_browser_acceptance.ps1 -ExtraPage <file>）",
  },
  async () => {
    const pageErrors = [];
    const blocked = [];
    const page = await browser.newPage();
    page.on("pageerror", function (error) {
      pageErrors.push(String(error && error.message ? error.message : error));
    });
    await page.addInitScript(REJECTION_HOOK);
    await page.route("**/*", (route) => {
      const target = route.request().url();
      if (target.startsWith("file://")) {
        return route.continue();
      }
      blocked.push(target);
      return route.abort();
    });

    await page.goto("file:///" + path.resolve(EXTRA_PAGE).replace(/\\/g, "/"));
    await page.waitForFunction(
      () => document.querySelectorAll("div.mermaid svg").length > 0,
      null,
      { timeout: 30000 },
    );

    const svgCount = await page.locator("div.mermaid svg").count();
    const katexCount = await page.locator(".katex").count();
    const imageSource = await page
      .locator('article img[alt="本地图片"]')
      .first()
      .getAttribute("src");
    const rejections = await page.evaluate(() => window.__mrRejections || []);

    assert.ok(svgCount >= 1, "Mermaid 容器里必须真的生成 <svg>：" + svgCount);
    assert.ok(katexCount >= 1, "KaTeX 公式必须渲染：" + katexCount);
    assert.ok(
      imageSource && imageSource.startsWith("data:image/png"),
      "本地图片必须内嵌成 data URI：" + imageSource,
    );
    assert.deepEqual(blocked, [], "离线页面不得发起任何非 file:// 请求");
    assert.deepEqual(pageErrors, []);
    assert.deepEqual(rejections, []);

    await page.close();
  },
);
