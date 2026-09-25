"use strict";

/**
 * 远程资源解析层（Phase 5C）。
 *
 * 三件事，都不做传输本身（传输在 http_client.js）：
 *   1) normalizeRemoteUrl：把作者引用归一成 fetch target（协议相对 → https）；
 *   2) createRemoteResolver：本次 conversion 的 URL 级 cache —— 同一 normalized URL 只创建**一个**
 *      Promise，重复引用（即使并发同时到达）复用同一个请求；成功与失败都缓存；
 *   3) runWithConcurrency：并发上限 4 的调度器；把结果写回 job，调用方按 job.index 顺序统一落盘，
 *      因此 manifest / warnings / HTML mutation 的顺序始终等于文档顺序，与网络完成顺序无关。
 *
 * cache 只存活于一次 conversion（不写磁盘、不跨进程、不跨文档）。
 */

const MAX_CONCURRENCY = 4;

// 协议相对 URL 用 HTTPS 抓取；失败时 HTML 仍保留作者原样（//host/x）。
function normalizeRemoteUrl(reference) {
  const raw = String(reference === undefined || reference === null ? "" : reference);
  if (/^data:/i.test(raw)) {
    return "";
  }
  if (/^https?:\/\//i.test(raw)) {
    return raw;
  }
  if (raw.startsWith("//")) {
    return "https:" + raw;
  }
  return "";
}

function toDataUri(result) {
  return "data:" + result.mimeType + ";base64," + result.bytes.toString("base64");
}

// 失败原因 → 用户可读短语。堆栈与细节不进用户 warning（留给 stderr / 内部结果）。
const REASON_TEXT = {
  timeout: "请求超时",
  network: "网络错误",
  "no-fetch": "运行时不支持网络请求",
  "content-type": "响应不是图片",
  "too-large": "超过大小上限",
  scheme: "重定向离开 HTTP(S)",
};

function reasonText(reason) {
  const key = String(reason === undefined || reason === null ? "" : reason);
  if (REASON_TEXT[key]) {
    return REASON_TEXT[key];
  }
  const match = key.match(/^http-(\d{3})$/);
  return match ? "HTTP " + match[1] : "未知原因";
}

function remoteFailureWarning(reference, reason) {
  return "远程资源无法内嵌，保留原引用：" + String(reference) + "（" + reasonText(reason) + "）";
}

/**
 * 本次 conversion 的远程解析器。
 * resolve() 先查 cache 再建 Promise：三个相同 URL 并发出现也只会有一次真实请求。
 */
function createRemoteResolver(options) {
  const settings = options || {};
  const client = settings.client;
  const cache = new Map();

  function resolve(fetchUrl) {
    if (!cache.has(fetchUrl)) {
      cache.set(fetchUrl, client.get(fetchUrl));
    }
    return cache.get(fetchUrl);
  }

  return {
    resolve: resolve,
    cachedCount: function () {
      return cache.size;
    },
  };
}

/** 并发上限内跑完 jobs；worker 自行把结果写回自己的 job。异常向上抛，不吞。 */
async function runWithConcurrency(jobs, limit, worker) {
  const list = jobs || [];
  if (!list.length) {
    return;
  }
  const requested = Number.isFinite(limit) && limit > 0 ? Math.floor(limit) : MAX_CONCURRENCY;
  const width = Math.max(1, Math.min(requested, list.length));
  let cursor = 0;
  const runners = [];
  for (let slot = 0; slot < width; slot += 1) {
    runners.push(
      (async function () {
        for (;;) {
          // 取号在 await 之前同步完成：两个 runner 不会拿到同一个 job。
          const index = cursor;
          cursor += 1;
          if (index >= list.length) {
            return;
          }
          await worker(list[index], index);
        }
      })(),
    );
  }
  await Promise.all(runners);
}

module.exports = {
  MAX_CONCURRENCY: MAX_CONCURRENCY,
  normalizeRemoteUrl: normalizeRemoteUrl,
  toDataUri: toDataUri,
  reasonText: reasonText,
  remoteFailureWarning: remoteFailureWarning,
  createRemoteResolver: createRemoteResolver,
  runWithConcurrency: runWithConcurrency,
};
