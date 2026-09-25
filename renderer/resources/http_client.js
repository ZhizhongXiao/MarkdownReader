"use strict";

/**
 * HTTP 传输层（Phase 5C）。
 *
 * 职责只有传输：GET、timeout、retry、redirect 结果、Content-Type 与大小校验。
 * 不做业务判断：不写 token、不写 manifest、不做跨引用去重（那些属 resources/remote_resolver.js）。
 *
 * 策略（implementation policy，不是长期 KEEP contract，只在本文件与测试里记录）：
 *   timeout 8000 ms / 次尝试；retries 1（总尝试 2 次）；retry delay 固定 150 ms；
 *   timeout / retries / maxBytes 只在「有限且为正」（retries 还须为非负整数）时生效，否则回落默认值；
 *   retry 只在 network error / timeout / HTTP 5xx；4xx 与内容校验失败（CT / size）不 retry；
 *   body 读取阶段的 AbortError / TimeoutError 与 fetch 阶段一样按 timeout 分类并 retry，其它读错误按 network
 *   分类并 retry，只有 too-large 不 retry；每次 retry 都是**完整重新 GET**（新 AbortSignal + 新 Response），
 *   绝不复用已失败的 body reader。
 *   单资源上限 16 MiB：Content-Length 超标立即拒绝（不读 body），否则读流累计超限即 abort；
 *   允许 http(s) 内重定向，返回 response.url 供审计；最终 URL 若不是 http(s) 视为失败。
 *
 * 用 Node 内置 fetch（Node >= 18），不引入 axios / node-fetch / got / request。
 * fetchImpl 可注入：测试用 fake fetch 做细粒度语义验证，不需要 socket / DNS。
 * 运行时缺 fetch（更老的 Node）时**降级**为可读失败，而不是崩溃。
 */

const DEFAULT_TIMEOUT_MS = 8_000;
const DEFAULT_RETRIES = 1;
const DEFAULT_RETRY_DELAY_MS = 150;
const DEFAULT_MAX_BYTES = 16 * 1024 * 1024;

// Content-Type 缺失时的回退：按 URL pathname 的已知图片扩展名判断（不做 magic-byte 嗅探）。
const MIME_BY_EXTENSION = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".bmp": "image/bmp",
};

function failure(reason, detail, retryable) {
  return {
    ok: false,
    reason: reason,
    detail: detail === undefined ? "" : String(detail),
    retryable: retryable === true,
  };
}

// readLimited 超限时用的内部哨兵：分类只看 error.name，不比对 message（message 是外部实现细节）。
const TOO_LARGE_NAME = "TooLargeError";

function tooLargeError() {
  const error = new Error("响应体超过大小上限");
  error.name = TOO_LARGE_NAME;
  return error;
}

/**
 * 传输失败分类（fetch 阶段与 body 读取阶段共用同一套规则）：
 *   TooLargeError → too-large，不 retry；
 *   AbortError / TimeoutError → timeout，retry（AbortSignal.timeout 与手动 abort 在 Node 上都以这两个 name 出现）；
 *   其它（socket 中断、连接被重置、流解析失败等）→ network，retry。
 */
function errorFailure(error) {
  const name = error && error.name ? String(error.name) : "";
  const detail = error && error.message ? error.message : String(error);
  if (name === TOO_LARGE_NAME) {
    return failure("too-large", detail, false);
  }
  if (name === "TimeoutError" || name === "AbortError") {
    return failure("timeout", detail, true);
  }
  return failure("network", detail, true);
}

function sleep(milliseconds) {
  return new Promise(function (resolve) {
    setTimeout(resolve, milliseconds);
  });
}

// Content-Type 可以带参数（例如 image/svg+xml; charset=utf-8）；只接受 image/*。
// 明显的 text/html / application/json（错误页 / 数据）因此自然被拒绝，不会被当图片内嵌。
function mimeTypeFromHeader(header) {
  if (!header) {
    return "";
  }
  const mime = String(header).split(";")[0].trim().toLowerCase();
  return mime.startsWith("image/") ? mime : "";
}

function mimeTypeFromUrl(url) {
  const pathname = String(url).split("?")[0].split("#")[0].toLowerCase();
  const dot = pathname.lastIndexOf(".");
  const extension = dot >= 0 ? pathname.slice(dot) : "";
  return MIME_BY_EXTENSION[extension] ? MIME_BY_EXTENSION[extension] : "";
}

function resolveMimeType(response, url) {
  const raw = response.headers && response.headers.get ? response.headers.get("content-type") : "";
  if (raw && String(raw).trim()) {
    // 有 Content-Type：只接受 image/*；显式的 text/html / application/json 一律拒绝，
    // 不得靠扩展名把它救回来（否则错误页会被当成图片内嵌）。
    return mimeTypeFromHeader(raw);
  }
  // 缺 Content-Type：才按 URL pathname 的已知图片扩展名回退。
  return mimeTypeFromUrl(url);
}

async function readLimited(response, maxBytes) {
  const body = response.body;
  if (!body || typeof body.getReader !== "function") {
    const buffer = Buffer.from(await response.arrayBuffer());
    if (buffer.length > maxBytes) {
      throw tooLargeError();
    }
    return buffer;
  }
  const reader = body.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const step = await reader.read();
    if (step.done) {
      break;
    }
    total += step.value.length;
    if (total > maxBytes) {
      try {
        await reader.cancel();
      } catch (_error) {
        // cancel 失败不影响结论：本次资源仍然按超限处理。
      }
      throw tooLargeError();
    }
    chunks.push(Buffer.from(step.value));
  }
  return Buffer.concat(chunks, total);
}

function createTimeoutSignal(timeoutMs, AbortControllerImpl) {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    return AbortSignal.timeout(timeoutMs);
  }
  if (typeof AbortControllerImpl === "function") {
    const controller = new AbortControllerImpl();
    const timer = setTimeout(function () {
      controller.abort();
    }, timeoutMs);
    if (typeof timer.unref === "function") {
      timer.unref();
    }
    return controller.signal;
  }
  return undefined;
}

/** 有限且为正的数字，否则回落默认值。 */
function positiveNumber(value, fallback) {
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

/** 非负整数，否则回落默认值（retries = 0 合法：只尝试一次）。 */
function nonNegativeInteger(value, fallback) {
  return Number.isInteger(value) && value >= 0 ? value : fallback;
}

/**
 * 造一个 HTTP client。生产默认 fetchImpl = globalThis.fetch；测试传 fake fetch。
 * 返回 { get(url), policy }；get() 永不抛错，失败一律返回 { ok: false, reason, retryable }。
 * 数值选项越界（非正数 / retries 为负或非整数）一律回落默认值；policy 给出的始终是真正生效的值。
 */
function createHttpClient(options) {
  const settings = options || {};
  const fetchImpl = settings.fetchImpl === undefined ? globalThis.fetch : settings.fetchImpl;
  // 选项只在有效范围内生效，否则回落默认值（负数 / 0 / NaN / Infinity 都不能穿透到重试循环与上限判断）。
  const timeoutMs = positiveNumber(settings.timeoutMs, DEFAULT_TIMEOUT_MS);
  const retries = nonNegativeInteger(settings.retries, DEFAULT_RETRIES);
  const retryDelayMs = Number.isFinite(settings.retryDelayMs)
    ? settings.retryDelayMs
    : DEFAULT_RETRY_DELAY_MS;
  const maxBytes = positiveNumber(settings.maxBytes, DEFAULT_MAX_BYTES);
  const AbortControllerImpl = settings.AbortControllerImpl || globalThis.AbortController;

  async function attempt(url) {
    if (typeof fetchImpl !== "function") {
      return failure("no-fetch", "运行时没有 fetch（需要 Node 18 或更新）", false);
    }

    let response = null;
    try {
      response = await fetchImpl(url, {
        method: "GET",
        redirect: "follow",
        signal: createTimeoutSignal(timeoutMs, AbortControllerImpl),
      });
    } catch (error) {
      // fetch 阶段不可能出现 too-large 哨兵；共用分类器保证两阶段规则一致。
      return errorFailure(error);
    }

    if (!response || typeof response.status !== "number") {
      return failure("network", "响应无效", true);
    }
    if (!response.ok) {
      const status = response.status;
      return failure("http-" + status, "HTTP " + status, status >= 500);
    }

    const finalUrl = String(response.url || url);
    if (!/^https?:/i.test(finalUrl)) {
      // 不跟随到非 HTTP(S)：远端不能把读取引到别的 scheme。
      return failure("scheme", "重定向离开 HTTP(S)：" + finalUrl, false);
    }

    const declaredHeader = response.headers ? response.headers.get("content-length") : null;
    const declared = Number(declaredHeader);
    if (Number.isFinite(declared) && declared > maxBytes) {
      return failure("too-large", "Content-Length " + declared + " 超过上限 " + maxBytes, false);
    }

    const mimeType = resolveMimeType(response, finalUrl);
    if (!mimeType) {
      return failure("content-type", "响应不是图片（Content-Type 与扩展名都无法判定）", false);
    }

    let bytes = null;
    try {
      bytes = await readLimited(response, maxBytes);
    } catch (error) {
      // 超限（哨兵）不 retry；读取阶段的 abort / socket 错误与 fetch 阶段同一分类，可 retry。
      return errorFailure(error);
    }

    return {
      ok: true,
      bytes: bytes,
      mimeType: mimeType,
      finalUrl: finalUrl,
      status: response.status,
    };
  }

  async function get(url) {
    let last = failure("network", "未发起请求", false);
    for (let attemptIndex = 0; attemptIndex <= retries; attemptIndex += 1) {
      last = await attempt(url);
      if (last.ok || !last.retryable || attemptIndex === retries) {
        return last;
      }
      if (retryDelayMs > 0) {
        await sleep(retryDelayMs);
      }
    }
    return last;
  }

  return {
    get: get,
    policy: {
      timeoutMs: timeoutMs,
      retries: retries,
      retryDelayMs: retryDelayMs,
      maxBytes: maxBytes,
    },
  };
}

module.exports = {
  createHttpClient: createHttpClient,
  resolveMimeType: resolveMimeType,
  mimeTypeFromHeader: mimeTypeFromHeader,
  mimeTypeFromUrl: mimeTypeFromUrl,
  DEFAULT_TIMEOUT_MS: DEFAULT_TIMEOUT_MS,
  DEFAULT_RETRIES: DEFAULT_RETRIES,
  DEFAULT_RETRY_DELAY_MS: DEFAULT_RETRY_DELAY_MS,
  DEFAULT_MAX_BYTES: DEFAULT_MAX_BYTES,
};
