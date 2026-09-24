"use strict";

/**
 * 本地文件 → data URI 的唯一实现（Phase 5A）。
 *
 * 与旧 production renderer（node_renderer/render.js 的 resolveImageSource）保持同一语义：
 *   - 只处理明确的本地路径；data: / http(s): / 协议相对 / 其它 scheme 一律不碰；
 *   - 读不到文件 → 返回 null（调用方保留原引用），并把**可读路径**写进 warnings；
 *   - 进程内 cache 只缓存成功结果（失败每次都要报出来，与旧实现一致）。
 */

const fs = require("fs");
const path = require("path");

const MIME_TYPES = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".bmp": "image/bmp",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".ttf": "font/ttf",
  ".otf": "font/otf",
};

const URI_SCHEME = /^[a-zA-Z][a-zA-Z0-9+.-]*:/;
const ABSOLUTE_WINDOWS = /^[a-zA-Z]:[\\/]/;
const REMOTE = /^(https?:)?\/\//i;

function mimeTypeFor(filePath) {
  return MIME_TYPES[path.extname(filePath).toLowerCase()] || "application/octet-stream";
}

// markdown-it 会把引用规范化成百分号编码，但那不是作者写下的文字。
function decodePath(value) {
  try {
    return decodeURI(String(value));
  } catch (_error) {
    return String(value);
  }
}

function isHandledReference(raw) {
  if (!raw) {
    return false;
  }
  if (/^data:/i.test(raw) || /^https?:/i.test(raw) || REMOTE.test(raw)) {
    return false;
  }
  // file: / mailto: 等其它 scheme 不处理（K13：file: 保持 markdown-it 默认结果）。
  return !URI_SCHEME.test(raw) || ABSOLUTE_WINDOWS.test(raw);
}

function createLocalFileReader() {
  const cache = new Map();

  return {
    /** 读取本地引用；返回 { dataUri, mimeType, absolute }，不处理或读取失败时返回 null。 */
    read: function (ref, baseDirectory, warnings, warningPrefix) {
      const raw = String(ref === undefined || ref === null ? "" : ref);
      if (!isHandledReference(raw)) {
        return null;
      }
      const decoded = decodePath(raw);
      const absolute = path.isAbsolute(decoded)
        ? path.normalize(decoded)
        : path.resolve(baseDirectory, decoded);
      if (cache.has(absolute)) {
        return cache.get(absolute);
      }

      let bytes = null;
      try {
        if (!fs.statSync(absolute).isFile()) {
          throw new Error("not a file");
        }
        bytes = fs.readFileSync(absolute);
      } catch (_error) {
        warnings.push(warningPrefix + decodePath(raw));
        return null;
      }

      const mimeType = mimeTypeFor(absolute);
      const result = {
        dataUri: "data:" + mimeType + ";base64," + bytes.toString("base64"),
        mimeType: mimeType,
        absolute: absolute,
      };
      cache.set(absolute, result);
      return result;
    },
  };
}

module.exports = {
  createLocalFileReader: createLocalFileReader,
  mimeTypeFor: mimeTypeFor,
  decodePath: decodePath,
  MIME_TYPES: MIME_TYPES,
};
