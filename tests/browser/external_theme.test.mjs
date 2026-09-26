"use strict";

/**
 * 外置主题（Phase 7F，opt-in 浏览器验收）。
 *
 * Python 与 jsdom 契约证明的是装配结果；这里补真实 Edge 里的另一半 —— 主题生效、
 * 本地资源已内嵌成 data URI、**零非 file:// 请求**（远程 url()/@import 若漏网会在这里
 * 露头），以及最关键的 Phase 7 验收第 3 条：**删掉主题目录后，已生成的 HTML 仍然可用**。
 *
 * 主题被装进一个临时目录（--external-root），因此这条用例不碰仓库自己的用户数据。
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
const CHANNEL = process.env.MR_BROWSER_CHANNEL || "msedge";
const THEME_ID = "paper";
const MARKER_COLOR = "rgb(1, 2, 3)";

// 1x1 PNG：主题 CSS 引用它，转换时必须内嵌，否则文档删掉主题后就不完整了。
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==",
  "base64",
);

const REJECTION_HOOK =
  "window.__mrRejections = [];" +
  "window.addEventListener('unhandledrejection', function (event) {" +
  "  window.__mrRejections.push(String(event.reason && event.reason.message ? event.reason.message : event.reason));" +
  "});";

let browser = null;
let workdir = null;
let themeRoot = null;
let pagePath = null;

function installTheme() {
  const theme = path.join(themeRoot, THEME_ID);
  fs.mkdirSync(path.join(theme, "assets"), { recursive: true });
  fs.writeFileSync(path.join(theme, "assets", "marker.png"), PNG);
  fs.writeFileSync(
    path.join(theme, "metadata.json"),
    JSON.stringify({ id: THEME_ID, name: "Paper", files: ["theme.css"] }),
    "utf8",
  );
  fs.writeFileSync(
    path.join(theme, "theme.css"),
    'html[data-theme-id="paper"]{color:' + MARKER_COLOR + ";background-image:url(assets/marker.png)}\n" +
      'html[data-theme-id="paper"] body.theme-paper .markdown-body{font-family:Georgia,serif}\n',
    "utf8",
  );
}

function assemble(outPath) {
  const completed = spawnSync(
    "uv",
    [
      "run",
      "python",
      "tools/assemble_document.py",
      "--out",
      outPath,
      "--template",
      THEME_ID,
      "--external-theme",
      THEME_ID,
      "--external-root",
      themeRoot,
    ],
    { cwd: REPO_ROOT, encoding: "utf8" },
  );
  assert.equal(
    completed.status,
    0,
    "装配带外置主题的页面失败：" + (completed.stderr || completed.stdout || completed.error),
  );
  assert.ok(fs.existsSync(outPath), "装配产物缺失：" + outPath);
}

before(async () => {
  let playwright = null;
  try {
    playwright = await import("playwright");
  } catch (error) {
    assert.fail("缺少 playwright（opt-in 依赖）：先执行 cd tests/browser; npm ci —— " + error.message);
  }
  try {
    browser = await playwright.chromium.launch({ channel: CHANNEL });
  } catch (error) {
    assert.fail("无法启动浏览器 channel=" + CHANNEL + "：" + error.message);
  }

  workdir = fs.mkdtempSync(path.join(os.tmpdir(), "mr-external-theme-"));
  themeRoot = path.join(workdir, "external");
  fs.mkdirSync(themeRoot, { recursive: true });
  installTheme();
  pagePath = path.join(workdir, "external-theme.html");
  assemble(pagePath);
});

after(async () => {
  if (browser) {
    await browser.close();
  }
  if (workdir) {
    fs.rmSync(workdir, { recursive: true, force: true });
  }
});

async function open() {
  const blocked = [];
  const pageErrors = [];
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
  await page.goto("file:///" + pagePath.replace(/\\/g, "/"));
  await page.waitForFunction(() => !!document.getElementById("markdown-body"));
  return { page, blocked, pageErrors };
}

function themeState(page) {
  return page.evaluate(() => ({
    themeId: document.documentElement.getAttribute("data-theme-id"),
    bodyClass: document.body.className,
    color: getComputedStyle(document.documentElement).color,
    background: getComputedStyle(document.documentElement).backgroundImage,
    bodyFont: getComputedStyle(document.getElementById("markdown-body")).fontFamily,
  }));
}

test("an external theme renders from the document alone", async () => {
  const session = await open();
  const page = session.page;
  try {
    const state = await themeState(page);

    assert.equal(state.themeId, THEME_ID, "文档默认主题就是该外置主题");
    assert.ok(state.bodyClass.indexOf("theme-" + THEME_ID) !== -1, state.bodyClass);
    assert.equal(state.color, MARKER_COLOR, "外置主题的 CSS 必须生效");
    assert.ok(state.bodyFont.indexOf("Georgia") !== -1, state.bodyFont);
    assert.ok(
      state.background.indexOf('url("data:image/png') === 0,
      "主题引用的本地图片必须已内嵌：" + state.background,
    );
    assert.ok(
      await page.locator("#theme-menu [data-theme-id='paper']").count(),
      "菜单必须提供这个外置主题",
    );

    const rejections = await page.evaluate(() => window.__mrRejections || []);
    assert.deepEqual(session.blocked, [], "外置主题不得引发任何非 file:// 请求");
    assert.deepEqual(session.pageErrors, []);
    assert.deepEqual(rejections, []);
  } finally {
    await page.close();
  }
});

test("the document still renders after the theme is removed", async () => {
  const session = await open();
  const page = session.page;
  try {
    fs.rmSync(path.join(themeRoot, THEME_ID), { recursive: true, force: true });
    await page.reload();
    await page.waitForFunction(() => !!document.getElementById("markdown-body"));

    const state = await themeState(page);
    assert.equal(state.themeId, THEME_ID, "文档仍然以该主题打开");
    assert.equal(state.color, MARKER_COLOR, "主题 CSS 已内嵌，删掉安装仍生效");
    assert.ok(state.background.indexOf('url("data:image/png') === 0, state.background);
    assert.deepEqual(session.blocked, []);
    assert.deepEqual(session.pageErrors, []);

    // 菜单仍能切回 builtin：文档自带的不只是这一套样式。
    await page.click("#btn-theme");
    await page.click('#theme-menu [data-theme-id="modern"]');
    const after = await themeState(page);
    assert.equal(after.themeId, "modern");
    assert.ok(after.color !== MARKER_COLOR, after.color);
  } finally {
    await page.close();
  }
});
