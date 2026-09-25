"use strict";

/**
 * 远程解析层单测（Phase 5C，node:test）。
 *
 * 覆盖：URL 归一化（协议相对 → https）、data URI 组装、用户可读失败文案、
 *      conversion-scoped cache（同一 URL 只请求一次、失败也缓存）、
 *      并发调度（上限 4 + 结果按 index 写回，完成顺序不影响结果顺序）。
 */

const assert = require("node:assert");
const { test } = require("node:test");

const {
  MAX_CONCURRENCY,
  normalizeRemoteUrl,
  toDataUri,
  reasonText,
  remoteFailureWarning,
  createRemoteResolver,
  runWithConcurrency,
} = require("../resources/remote_resolver");

function sleep(milliseconds) {
  return new Promise(function (resolve) {
    setTimeout(resolve, milliseconds);
  });
}

test("MAX_CONCURRENCY is the frozen policy value", function () {
  assert.strictEqual(MAX_CONCURRENCY, 4);
});

test("normalizeRemoteUrl turns protocol-relative references into HTTPS targets", function () {
  assert.strictEqual(normalizeRemoteUrl("https://cdn.invalid/a.png"), "https://cdn.invalid/a.png");
  assert.strictEqual(normalizeRemoteUrl("http://cdn.invalid/a.png"), "http://cdn.invalid/a.png");
  assert.strictEqual(normalizeRemoteUrl("//cdn.invalid/a.png"), "https://cdn.invalid/a.png");
});

test("normalizeRemoteUrl refuses everything that must not be fetched", function () {
  assert.strictEqual(normalizeRemoteUrl("data:image/png;base64,AAA"), "");
  assert.strictEqual(normalizeRemoteUrl("file:///C:/a.png"), "");
  assert.strictEqual(normalizeRemoteUrl("mailto:someone@example.invalid"), "");
  assert.strictEqual(normalizeRemoteUrl("ftp://example.invalid/a.png"), "");
  assert.strictEqual(normalizeRemoteUrl("pic.png"), "");
  assert.strictEqual(normalizeRemoteUrl(""), "");
  assert.strictEqual(normalizeRemoteUrl(undefined), "");
});

test("toDataUri assembles a data URI from the fetched bytes", function () {
  assert.strictEqual(
    toDataUri({ mimeType: "image/png", bytes: Buffer.from("ab", "utf8") }),
    "data:image/png;base64,YWI=",
  );
});

test("failure reasons become short user-readable phrases", function () {
  assert.strictEqual(reasonText("timeout"), "请求超时");
  assert.strictEqual(reasonText("network"), "网络错误");
  assert.strictEqual(reasonText("no-fetch"), "运行时不支持网络请求");
  assert.strictEqual(reasonText("content-type"), "响应不是图片");
  assert.strictEqual(reasonText("too-large"), "超过大小上限");
  assert.strictEqual(reasonText("scheme"), "重定向离开 HTTP(S)");
  assert.strictEqual(reasonText("http-404"), "HTTP 404");
  assert.strictEqual(reasonText("http-503"), "HTTP 503");
  assert.strictEqual(reasonText("something-else"), "未知原因");
});

test("the failure warning keeps the author reference and a short reason", function () {
  assert.strictEqual(
    remoteFailureWarning("//cdn.invalid/a.png", "http-404"),
    "远程资源无法内嵌，保留原引用：//cdn.invalid/a.png（HTTP 404）",
  );
});

test("the same URL is requested once even when three references resolve concurrently", async function () {
  let calls = 0;
  const client = {
    get: async function (url) {
      calls += 1;
      await sleep(5);
      return { ok: true, mimeType: "image/png", bytes: Buffer.from("x", "utf8"), finalUrl: url };
    },
  };
  const resolver = createRemoteResolver({ client: client });
  const url = "https://cdn.invalid/a.png";

  const results = await Promise.all([
    resolver.resolve(url),
    resolver.resolve(url),
    resolver.resolve(url),
  ]);

  assert.strictEqual(calls, 1, "同一 URL 只能有一次真实请求");
  assert.strictEqual(new Set(results).size, 1, "三处必须复用同一个 Promise 的结果");
  assert.strictEqual(resolver.cachedCount(), 1);
});

test("a failure is cached as well", async function () {
  let calls = 0;
  const client = {
    get: async function () {
      calls += 1;
      return { ok: false, reason: "http-404", retryable: false };
    },
  };
  const resolver = createRemoteResolver({ client: client });

  const first = await resolver.resolve("https://cdn.invalid/missing.png");
  const second = await resolver.resolve("https://cdn.invalid/missing.png");

  assert.strictEqual(calls, 1);
  assert.strictEqual(first, second);
  assert.strictEqual(first.reason, "http-404");
});

test("different URLs are requested separately", async function () {
  const seen = [];
  const client = {
    get: async function (url) {
      seen.push(url);
      return { ok: true, mimeType: "image/png", bytes: Buffer.alloc(0), finalUrl: url };
    },
  };
  const resolver = createRemoteResolver({ client: client });

  await resolver.resolve("https://cdn.invalid/a.png");
  await resolver.resolve("https://cdn.invalid/b.png");

  assert.deepStrictEqual(seen, ["https://cdn.invalid/a.png", "https://cdn.invalid/b.png"]);
});

test("runWithConcurrency keeps the limit and writes results by index", async function () {
  const jobs = [];
  for (let index = 0; index < 12; index += 1) {
    jobs.push({ index: index, value: null });
  }
  let inFlight = 0;
  let maxInFlight = 0;
  const completionOrder = [];

  await runWithConcurrency(jobs, MAX_CONCURRENCY, async function (job) {
    inFlight += 1;
    maxInFlight = Math.max(maxInFlight, inFlight);
    // 第 0 个最慢：完成顺序与文档顺序刻意不同。
    await sleep(job.index === 0 ? 40 : 5);
    job.value = job.index;
    completionOrder.push(job.index);
    inFlight -= 1;
  });

  assert.ok(maxInFlight <= MAX_CONCURRENCY, "并发不得超过上限：" + maxInFlight);
  assert.ok(maxInFlight >= 2, "应当真的并发执行：" + maxInFlight);
  assert.deepStrictEqual(
    jobs.map((job) => job.value),
    jobs.map((job) => job.index),
    "结果必须按 index 落位",
  );
  assert.notStrictEqual(completionOrder[0], 0, "最慢的第一个 job 不应最先完成（顺序确实解耦）");
});

test("runWithConcurrency handles an empty job list", async function () {
  let calls = 0;

  await runWithConcurrency([], MAX_CONCURRENCY, async function () {
    calls += 1;
  });

  assert.strictEqual(calls, 0);
});
