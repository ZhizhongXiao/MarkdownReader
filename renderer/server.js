"use strict";

const readline = require("node:readline");
const { ProtocolError, validateRequest, errorEnvelope, serialize } = require("./protocol");
const { renderEnvelope } = require("./render_request");

const SESSION_PROTOCOL = 1;

async function handleLine(line) {
  let id = null;
  let request;
  try {
    let frame;
    try {
      frame = JSON.parse(line);
    } catch (error) {
      throw new ProtocolError("invalid_json", "JSONL 请求不是合法 JSON。", error.message);
    }
    if (frame && typeof frame.id === "string") {
      id = frame.id;
    }
    if (!frame || frame.protocol !== SESSION_PROTOCOL) {
      throw new ProtocolError("invalid_protocol", "JSONL protocol 必须为 1。");
    }
    if (id === null || id.length === 0) {
      throw new ProtocolError("invalid_request", "JSONL id 必须为非空字符串。");
    }
    request = validateRequest(frame.request);
  } catch (error) {
    return response(id, errorEnvelope(
      error instanceof ProtocolError ? error.code : "invalid_request",
      error.message,
      error instanceof ProtocolError ? error.detail : "",
    ));
  }

  try {
    return response(id, await renderEnvelope(request));
  } catch (error) {
    return response(id, errorEnvelope("render_failed", "渲染失败。", error.message));
  }
}

function response(id, envelope) {
  if (!envelope.ok) {
    process.stderr.write("[renderer] " + envelope.error.code + ": " + envelope.error.message + "\n");
  }
  return { protocol: SESSION_PROTOCOL, id, response: envelope };
}

async function serve() {
  const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  // Sequential processing also isolates module-level plugin state between requests.
  for await (const line of lines) {
    const frame = await handleLine(line);
    // Await each write, including backpressure from multi-MB KaTeX/Mermaid envelopes.
    await new Promise(function (resolve, reject) {
      process.stdout.write(serialize(frame), function (error) {
        if (error) reject(error);
        else resolve();
      });
    });
  }
}

module.exports = { serve };
