"use strict";

/**
 * HTTP 传输层单测（Phase 5C，node:test）：注入 fake fetch，**不碰 socket / DNS**。
 *
 * 覆盖：成功、retry（5xx / network / timeout）、不 retry（4xx / Content-Type / 大小）、
 *      Content-Length 与流式两种大小限制、redirect 的 finalUrl 与非 HTTP(S) 拒绝、
 *      Content-Type 校验与扩展名回退、缺 fetch 的降级。
 *
 * 这是 implementation policy 的细粒度证明；端到端（真实 dist + loopback）在
 * tests/test_renderer_network.py。
 */

const assert = require("node:assert");
const { test } = require("node:test");

const {
  createHttpClient,
  mimeTypeFromHeader,
  mimeTypeFromUrl,
  DEFAULT_TIMEOUT_MS,
  DEFAULT_RETRIES,
  DEFAULT_RETRY_DELAY_MS,
  DEFAULT_MAX_BYTES,
} = require("../resources/http_client");

const PNG_BYTES = Buffer.from("89504e470d0a1a0a", "hex");

function headerMap(values) {
  const lower = {};
  for (const key of Object.keys(values || {})) {
    lower[key.toLowerCase()] = values[key];
  }
  return {
    get: function (name) {
      const target = String(name).toLowerCase();
      return Object.prototype.hasOwnProperty.call(lower, target) ? lower[target] : null;
    },
  };
}

function fakeResponse(options) {
  const settings = options || {};
  const status = settings.status === undefined ? 200 : settings.status;
  const bytes = settings.bytes || PNG_BYTES;
  const state = { read: false };
  return {
    state: state,
    ok: status >= 200 && status < 300,
    status: status,
    url: settings.url,
    headers: headerMap(settings.headers),
    body: {
      getReader: function () {
        let sent = false;
        return {
          read: async function () {
            state.read = true;
            if (settings.bodyError) {
              // 头已正常返回、body 读取失败（timeout / socket / 流错误）的分类测试用。
              throw settings.bodyError;
            }
            if (sent) {
              return { done: true };
            }
            sent = true;
            return { done: false, value: bytes };
          },
          cancel: async function () {
            return undefined;
          },
        };
      },
    },
  };
}

function imageHeaders(overrides) {
  return Object.assign({ "content-type": "image/png" }, overrides || {});
}

/** handler 收到 (url, attemptIndex)；calls 记录每次真实请求（含 init）。 */
function clientWith(handler, options) {
  const calls = [];
  const client = createHttpClient(
    Object.assign(
      {
        fetchImpl: async function (url, init) {
          calls.push({ url: url, init: init });
          return handler(url, calls.length - 1);
        },
        retryDelayMs: 0,
      },
      options || {},
    ),
  );
  return { client: client, calls: calls };
}

test("policy defaults are the frozen 5C values", function () {
  const client = createHttpClient({ fetchImpl: async function () {} });

  assert.deepStrictEqual(client.policy, {
    timeoutMs: DEFAULT_TIMEOUT_MS,
    retries: DEFAULT_RETRIES,
    retryDelayMs: DEFAULT_RETRY_DELAY_MS,
    maxBytes: DEFAULT_MAX_BYTES,
  });
  assert.strictEqual(DEFAULT_TIMEOUT_MS, 8000);
  assert.strictEqual(DEFAULT_RETRIES, 1);
  assert.strictEqual(DEFAULT_RETRY_DELAY_MS, 150);
  assert.strictEqual(DEFAULT_MAX_BYTES, 16 * 1024 * 1024);
});

test("invalid numeric options fall back to the defaults", function () {
  const allInvalid = createHttpClient({
    fetchImpl: async function () {},
    timeoutMs: -1,
    retries: -1,
    maxBytes: 0,
  });
  assert.deepStrictEqual(allInvalid.policy, {
    timeoutMs: DEFAULT_TIMEOUT_MS,
    retries: DEFAULT_RETRIES,
    retryDelayMs: DEFAULT_RETRY_DELAY_MS,
    maxBytes: DEFAULT_MAX_BYTES,
  });

  for (const timeoutMs of [0, -5, Number.NaN, Number.POSITIVE_INFINITY, "8000"]) {
    const client = createHttpClient({ fetchImpl: async function () {}, timeoutMs: timeoutMs });
    assert.strictEqual(client.policy.timeoutMs, DEFAULT_TIMEOUT_MS, "timeoutMs=" + String(timeoutMs));
  }
  for (const retries of [-1, -10, 1.5, Number.NaN, Number.POSITIVE_INFINITY, "1"]) {
    const client = createHttpClient({ fetchImpl: async function () {}, retries: retries });
    assert.strictEqual(client.policy.retries, DEFAULT_RETRIES, "retries=" + String(retries));
  }
  for (const maxBytes of [0, -1, Number.NaN, "1024"]) {
    const client = createHttpClient({ fetchImpl: async function () {}, maxBytes: maxBytes });
    assert.strictEqual(client.policy.maxBytes, DEFAULT_MAX_BYTES, "maxBytes=" + String(maxBytes));
  }
});

test("valid numeric options are honored", function () {
  const client = createHttpClient({
    fetchImpl: async function () {},
    timeoutMs: 300,
    retries: 0,
    retryDelayMs: 0,
    maxBytes: 2048,
  });

  assert.deepStrictEqual(client.policy, {
    timeoutMs: 300,
    retries: 0,
    retryDelayMs: 0,
    maxBytes: 2048,
  });
});

test("a negative retries option still issues the default number of attempts", async function () {
  const fake = clientWith(function () {
    return fakeResponse({ status: 503, headers: imageHeaders() });
  }, { retries: -1 });

  const result = await fake.client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "http-503");
  assert.strictEqual(fake.calls.length, 2, "负数必须回落默认 1（共 2 次尝试），而不是一次请求都不发");
});

test("a successful image response returns bytes, mime and the final URL", async function () {
  const fake = clientWith(function () {
    return fakeResponse({ headers: imageHeaders(), url: "https://cdn.example.invalid/a.png" });
  });

  const result = await fake.client.get("https://cdn.example.invalid/a.png");

  assert.strictEqual(result.ok, true);
  assert.strictEqual(result.mimeType, "image/png");
  assert.strictEqual(result.finalUrl, "https://cdn.example.invalid/a.png");
  assert.deepStrictEqual(result.bytes, PNG_BYTES);
  assert.strictEqual(fake.calls.length, 1);
});

test("the request carries a timeout signal", async function () {
  const fake = clientWith(function () {
    return fakeResponse({ headers: imageHeaders() });
  });

  await fake.client.get("https://cdn.example.invalid/a.png");

  assert.ok(fake.calls[0].init.signal, "必须传 AbortSignal 作为超时信号");
  assert.strictEqual(fake.calls[0].init.method, "GET");
  assert.strictEqual(fake.calls[0].init.redirect, "follow");
});

test("an HTML error page is not accepted as an image and is not retried", async function () {
  const fake = clientWith(function () {
    return fakeResponse({
      headers: { "content-type": "text/html; charset=utf-8" },
      url: "https://x.invalid/a.png",
    });
  });

  const result = await fake.client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "content-type");
  assert.strictEqual(fake.calls.length, 1, "内容校验失败不 retry");
});

test("Content-Type parameters are understood", async function () {
  const fake = clientWith(function () {
    return fakeResponse({ headers: { "content-type": "image/svg+xml; charset=utf-8" } });
  });

  const result = await fake.client.get("https://x.invalid/a.svg");

  assert.strictEqual(result.ok, true);
  assert.strictEqual(result.mimeType, "image/svg+xml");
});

test("a missing Content-Type falls back to the URL extension", async function () {
  const fake = clientWith(function () {
    return fakeResponse({ headers: {}, bytes: Buffer.from("<svg/>", "utf8") });
  });

  const result = await fake.client.get("https://x.invalid/diagram.svg?v=2");

  assert.strictEqual(result.ok, true);
  assert.strictEqual(result.mimeType, "image/svg+xml");
});

test("a missing Content-Type without a known image extension is refused", async function () {
  const fake = clientWith(function () {
    return fakeResponse({ headers: {} });
  });

  const result = await fake.client.get("https://x.invalid/some/path");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "content-type");
});

test("a 5xx response is retried once and can then succeed", async function () {
  const fake = clientWith(function (url, index) {
    if (index === 0) {
      return fakeResponse({ status: 503, headers: {}, url: url });
    }
    return fakeResponse({ headers: imageHeaders(), url: url });
  });

  const result = await fake.client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, true);
  assert.strictEqual(fake.calls.length, 2);
});

test("a persistent 5xx gives up after the single retry", async function () {
  const fake = clientWith(function (url) {
    return fakeResponse({ status: 500, headers: {}, url: url });
  });

  const result = await fake.client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "http-500");
  assert.strictEqual(fake.calls.length, 2);
});

test("a 4xx response is not retried", async function () {
  const fake = clientWith(function (url) {
    return fakeResponse({ status: 404, headers: {}, url: url });
  });

  const result = await fake.client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "http-404");
  assert.strictEqual(fake.calls.length, 1);
});

test("a network error is retried", async function () {
  const fake = clientWith(function () {
    throw new TypeError("fetch failed");
  });

  const result = await fake.client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "network");
  assert.strictEqual(fake.calls.length, 2);
});

test("a timeout is reported as timeout and retried", async function () {
  const fake = clientWith(function () {
    const error = new Error("The operation was aborted due to timeout");
    error.name = "TimeoutError";
    throw error;
  });

  const result = await fake.client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "timeout");
  assert.strictEqual(fake.calls.length, 2);
});

test("a body read timeout is reported as timeout and retried with a fresh GET", async function () {
  const timeoutError = new Error("The operation was aborted due to timeout");
  timeoutError.name = "TimeoutError";
  let responses = 0;
  const fake = clientWith(function () {
    responses += 1;
    return fakeResponse({ headers: imageHeaders(), bodyError: timeoutError });
  });

  const result = await fake.client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "timeout", "body 读取阶段的 abort 必须按 timeout 分类");
  assert.strictEqual(result.retryable, true);
  assert.strictEqual(fake.calls.length, 2, "body 读取阶段的超时必须 retry");
  assert.strictEqual(responses, 2);
  assert.strictEqual(fake.calls[0].init.method, "GET");
  assert.strictEqual(fake.calls[1].init.method, "GET");
  assert.notStrictEqual(
    fake.calls[0].init.signal,
    fake.calls[1].init.signal,
    "retry 必须重新发起完整 GET（新 AbortSignal），不能复用已失败的 body reader",
  );
});

test("a body read failure is reported as network and retried", async function () {
  const fake = clientWith(function () {
    return fakeResponse({ headers: imageHeaders(), bodyError: new TypeError("terminated") });
  });

  const result = await fake.client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "network");
  assert.strictEqual(result.retryable, true);
  assert.strictEqual(fake.calls.length, 2);
});

test("a read error is classified by name, not by its message", async function () {
  const impostor = new Error("too-large");
  impostor.name = "TypeError";
  const fake = clientWith(function () {
    return fakeResponse({ headers: imageHeaders(), bodyError: impostor });
  });

  const result = await fake.client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "network", "分类只看 error.name，不比对 message");
  assert.strictEqual(fake.calls.length, 2);
});

test("an oversized Content-Length is refused without reading the body", async function () {
  const oversized = fakeResponse({
    headers: imageHeaders({ "content-length": String(2 * 1024 * 1024) }),
  });
  const fake = clientWith(function () {
    return oversized;
  }, { maxBytes: 1024 });

  const result = await fake.client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "too-large");
  assert.strictEqual(oversized.state.read, false, "Content-Length 已超标时不得读取 body");
  assert.strictEqual(fake.calls.length, 1, "大小超限不 retry");
});

test("a streaming body that exceeds the limit is aborted", async function () {
  const fake = clientWith(function () {
    return fakeResponse({ headers: imageHeaders(), bytes: Buffer.alloc(4096) });
  }, { maxBytes: 1024 });

  const result = await fake.client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "too-large");
  assert.strictEqual(fake.calls.length, 1);
});

test("a redirect is followed and its final URL is reported", async function () {
  const fake = clientWith(function () {
    return fakeResponse({ headers: imageHeaders(), url: "https://mirror.invalid/final.png" });
  });

  const result = await fake.client.get("https://origin.invalid/a.png");

  assert.strictEqual(result.ok, true);
  assert.strictEqual(result.finalUrl, "https://mirror.invalid/final.png");
});

test("a final URL outside HTTP(S) is refused", async function () {
  const fake = clientWith(function () {
    return fakeResponse({ headers: imageHeaders(), url: "file:///etc/passwd" });
  });

  const result = await fake.client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "scheme");
  assert.strictEqual(fake.calls.length, 1);
});

test("a runtime without fetch degrades to a readable failure", async function () {
  const client = createHttpClient({ fetchImpl: null });

  const result = await client.get("https://x.invalid/a.png");

  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.reason, "no-fetch");
  assert.strictEqual(result.retryable, false);
});

test("mime helpers only accept image types", function () {
  assert.strictEqual(mimeTypeFromHeader("image/png"), "image/png");
  assert.strictEqual(mimeTypeFromHeader("IMAGE/WEBP; charset=binary"), "image/webp");
  assert.strictEqual(mimeTypeFromHeader("text/html"), "");
  assert.strictEqual(mimeTypeFromHeader("application/json"), "");
  assert.strictEqual(mimeTypeFromHeader(""), "");
  assert.strictEqual(mimeTypeFromUrl("https://x.invalid/a.JPEG?x=1"), "image/jpeg");
  assert.strictEqual(mimeTypeFromUrl("https://x.invalid/a.txt"), "");
  assert.strictEqual(mimeTypeFromUrl("https://x.invalid/a"), "");
});
