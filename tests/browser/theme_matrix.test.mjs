"use strict";

/**
 * 主题矩阵（Phase 6C，opt-in 浏览器验收）。
 *
 * jsdom 契约证明的是状态与 DOM：初始主题、切换、持久化、回落、DOM identity、与明暗正交。
 * 这里补的是只有真实浏览器才能回答的那一半 —— **三套主题的 CSS 同时在一份 HTML 里，
 * 到底谁生效**：`html[data-theme-id]` 选 token、`body.theme-<id>` 选组件规则，
 * 而 print 下必须回到白纸黑字。
 *
 * 页面由项目自己的装配器生成（`tools/assemble_document.py --template <id>`），
 * 因此验的是真实产物，而不是测试里另写一份。
 *
 * 配置：`MR_BROWSER_CHANNEL`（默认 msedge）。
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

const THEMES = ["modern", "office", "vscode"];
// Office 的组件级差异：主题 token 之外的规则（正文衬线字体），
// 它是"Office 的组件选择器必须被定域"这条最直接的可观测证据。
const OFFICE_FONT = "Times New Roman";

const REJECTION_HOOK =
  "window.__mrRejections = [];" +
  "window.addEventListener('unhandledrejection', function (event) {" +
  "  window.__mrRejections.push(String(event.reason && event.reason.message ? event.reason.message : event.reason));" +
  "});";

let browser = null;
let workdir = null;
const built = {};

function assemble(templateId, outPath) {
  const completed = spawnSync(
    "uv",
    ["run", "python", "tools/assemble_document.py", "--out", outPath, "--template", templateId],
    { cwd: REPO_ROOT, encoding: "utf8" },
  );
  assert.equal(
    completed.status,
    0,
    "装配 " + templateId + " 失败：" + (completed.stderr || completed.stdout || completed.error),
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

  workdir = fs.mkdtempSync(path.join(os.tmpdir(), "mr-theme-"));
  built.modern = path.join(workdir, "theme-modern.html");
  built.office = path.join(workdir, "theme-office.html");
  assemble("modern", built.modern);
  assemble("office", built.office);
});

after(async () => {
  if (browser) {
    await browser.close();
  }
  if (workdir) {
    fs.rmSync(workdir, { recursive: true, force: true });
  }
});

async function open(file) {
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
  await page.goto("file:///" + path.resolve(file).replace(/\\/g, "/"));
  await page.waitForFunction(() => !!document.getElementById("markdown-body"));
  return { page, pageErrors, blocked };
}

function themeState(page) {
  return page.evaluate(() => ({
    themeId: document.documentElement.getAttribute("data-theme-id"),
    bodyClass: document.body.className,
    dark: document.documentElement.getAttribute("data-theme") === "dark",
    background: getComputedStyle(document.documentElement).getPropertyValue("--color-bg").trim(),
    bodyFont: getComputedStyle(document.getElementById("markdown-body")).fontFamily,
    bodyColor: getComputedStyle(document.body).color,
    htmlBackground: getComputedStyle(document.documentElement).backgroundColor,
    bodyBackground: getComputedStyle(document.body).backgroundColor,
    contentBackground: getComputedStyle(document.getElementById("content-area")).backgroundColor,
  }));
}

async function selectTheme(page, themeId) {
  await page.click("#btn-theme");
  await page.click('#theme-menu [data-theme-id="' + themeId + '"]');
}

async function setDark(page, wanted) {
  const state = await themeState(page);
  if (state.dark !== wanted) {
    await page.click("#btn-dark-mode");
  }
  const after = await themeState(page);
  assert.equal(after.dark, wanted, "明暗切换未生效（wanted " + wanted + "）");
}

test("the document starts on the theme its author converted with", async () => {
  const modern = await open(built.modern);
  const office = await open(built.office);
  try {
    const modernState = await themeState(modern.page);
    const officeState = await themeState(office.page);

    assert.equal(modernState.themeId, "modern");
    assert.ok(modernState.bodyClass.indexOf("theme-modern") !== -1, modernState.bodyClass);
    assert.equal(officeState.themeId, "office");
    assert.ok(officeState.bodyClass.indexOf("theme-office") !== -1, officeState.bodyClass);
    assert.ok(
      officeState.bodyFont.indexOf(OFFICE_FONT) !== -1,
      "Office 文档必须用 Office 的正文字体：" + officeState.bodyFont,
    );
    assert.ok(
      modernState.bodyFont.indexOf(OFFICE_FONT) === -1,
      "Modern 文档不得套用 Office 组件规则：" + modernState.bodyFont,
    );
  } finally {
    await modern.page.close();
    await office.page.close();
  }
});

test("theme matrix: three themes x two colour schemes", async () => {
  const session = await open(built.modern);
  const page = session.page;
  try {
    const observed = [];
    for (const themeId of THEMES) {
      await selectTheme(page, themeId);
      for (const dark of [false, true]) {
        await setDark(page, dark);
        const label = themeId + (dark ? " + dark" : " + light");
        const state = await themeState(page);

        assert.equal(state.themeId, themeId, label + "：data-theme-id");
        assert.ok(
          state.bodyClass.indexOf("theme-" + themeId) !== -1,
          label + "：body class = " + state.bodyClass,
        );
        for (const other of THEMES) {
          if (other === themeId) continue;
          assert.ok(
            state.bodyClass.indexOf("theme-" + other) === -1,
            label + "：不得同时带 " + other + " 的 class（" + state.bodyClass + "）",
          );
        }
        assert.equal(state.dark, dark, label + "：明暗与主题正交");
        assert.ok(state.background.length > 0, label + "：--color-bg 必须解析出值");
        if (themeId === "office") {
          assert.ok(
            state.bodyFont.indexOf(OFFICE_FONT) !== -1,
            label + "：Office 组件规则必须生效：" + state.bodyFont,
          );
        } else {
          assert.ok(
            state.bodyFont.indexOf(OFFICE_FONT) === -1,
            label + "：Office 组件规则不得泄漏：" + state.bodyFont,
          );
        }
        observed.push(label + " bg=" + state.background + " font=" + state.bodyFont);
      }
    }
    assert.equal(observed.length, 6, observed.join(" | "));

    const rejections = await page.evaluate(() => window.__mrRejections || []);
    assert.deepEqual(session.blocked, [], "切换主题不得发起任何非 file:// 请求");
    assert.deepEqual(session.pageErrors, []);
    assert.deepEqual(rejections, []);
  } finally {
    await page.close();
  }
});

test("print returns to white paper and black text in every combination", async () => {
  const session = await open(built.modern);
  const page = session.page;
  try {
    for (const themeId of THEMES) {
      await selectTheme(page, themeId);
      for (const dark of [false, true]) {
        await setDark(page, dark);
        await page.emulateMedia({ media: "print" });
        const state = await themeState(page);
        const label = themeId + (dark ? " + dark" : " + light");

        assert.equal(state.htmlBackground, "rgb(255, 255, 255)", label + "：画布必须回到白纸");
        assert.equal(state.bodyBackground, "rgb(255, 255, 255)", label + "：正文底色必须回到白纸");
        assert.equal(state.bodyColor, "rgb(0, 0, 0)", label + "：打印文字必须是黑色");
        if (dark) {
          // 这条就是 specificity 修复本身：主题自己的暗色 token 必须被共享打印样式压回白色。
          assert.equal(
            state.background.toLowerCase(),
            "#ffffff",
            label + "：暗色下 --color-bg 必须被 print.css 压回 #ffffff",
          );
        }
        await page.emulateMedia({ media: "screen" });
      }
    }
  } finally {
    await page.close();
  }
});
