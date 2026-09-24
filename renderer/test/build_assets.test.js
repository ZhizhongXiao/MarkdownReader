"use strict";

/**
 * 资产发布逻辑的单元测试（Phase 5B，node:test）。
 *
 * 只测 build.js 导出的纯函数：vendored runtime 的来源校验、staging 复验、受管名字的替换。
 * 不跑 esbuild、不碰真实 dist、不联网；集成层（真实构建后的 dist 状态、篡改 vendor 时拒绝构建
 * 且不动 dist）由 Python 侧 tests/test_renderer_build_assets.py 与
 * tests/test_renderer_adapter_mermaid_runtime.py 覆盖。
 */

const assert = require("node:assert");
const { test } = require("node:test");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const build = require("../build/build.js");

const RENDERER_ROOT = path.resolve(__dirname, "..");
const REPO_ROOT = path.resolve(RENDERER_ROOT, "..");
const VENDOR_ROOT = path.join(RENDERER_ROOT, "vendor", "mermaid");
const VENDOR_VERSION = "11.15.0";

function tempDirectory() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "mr-build-assets-"));
}

function sha256File(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

/** 造一个 fixture 仓库：vendor/<version>/ 里是真实产物，metadata / 产物可被改动。 */
function fixtureRepo(options) {
  const repo = tempDirectory();
  const version = (options && options.version) || VENDOR_VERSION;
  const directory = path.join(repo, "renderer", "vendor", "mermaid", version);
  fs.mkdirSync(directory, { recursive: true });
  const artifact = path.join(directory, "mermaid.min.js");
  fs.copyFileSync(path.join(VENDOR_ROOT, VENDOR_VERSION, "mermaid.min.js"), artifact);
  fs.copyFileSync(path.join(VENDOR_ROOT, VENDOR_VERSION, "LICENSE"), path.join(directory, "LICENSE"));

  const metadata = JSON.parse(
    fs.readFileSync(path.join(VENDOR_ROOT, VENDOR_VERSION, "metadata.json"), "utf8"),
  );
  metadata.version = version;
  metadata.artifact_sha256 = sha256File(artifact);
  metadata.artifact_bytes = fs.statSync(artifact).size;
  if (options && options.metadataPatch) {
    options.metadataPatch(metadata);
  }
  fs.writeFileSync(
    path.join(directory, "metadata.json"),
    JSON.stringify(metadata, null, 2) + "\n",
    "utf8",
  );
  if (options && options.tamperArtifact) {
    fs.appendFileSync(artifact, "// tampered\n");
  }
  return repo;
}

test("the committed vendor directory passes the build gate", function () {
  const vendor = build.verifyVendoredMermaid(REPO_ROOT);

  assert.deepStrictEqual(vendor.problems, []);
  assert.strictEqual(vendor.ok, true);
  assert.strictEqual(vendor.version, VENDOR_VERSION);
  assert.strictEqual(vendor.sha256, vendor.metadata.artifact_sha256);
  assert.strictEqual(vendor.sha256, sha256File(vendor.artifactPath));
});

test("a tampered artifact is refused with the hash problem spelled out", function () {
  const vendor = build.verifyVendoredMermaid(fixtureRepo({ tamperArtifact: true }));

  assert.strictEqual(vendor.ok, false);
  assert.ok(
    vendor.problems.some(function (item) {
      return item.includes("SHA-256");
    }),
    JSON.stringify(vendor.problems),
  );
});

test("a metadata version that disagrees with the directory name is refused", function () {
  const repo = fixtureRepo({
    metadataPatch: function (metadata) {
      metadata.version = "0.0.0";
    },
  });

  const vendor = build.verifyVendoredMermaid(repo);

  assert.strictEqual(vendor.ok, false);
  assert.ok(vendor.problems.some((item) => item.includes("与目录名")), vendor.problems);
});

test("a missing license is refused", function () {
  const repo = fixtureRepo();
  fs.rmSync(path.join(repo, "renderer", "vendor", "mermaid", VENDOR_VERSION, "LICENSE"));

  const vendor = build.verifyVendoredMermaid(repo);

  assert.strictEqual(vendor.ok, false);
  assert.ok(vendor.problems.some((item) => item.includes("许可证")), vendor.problems);
});

test("more than one version directory is refused instead of guessing", function () {
  const repo = fixtureRepo();
  const other = path.join(repo, "renderer", "vendor", "mermaid", "9.9.9");
  fs.mkdirSync(other, { recursive: true });
  fs.writeFileSync(path.join(other, "metadata.json"), "{}\n", "utf8");

  const vendor = build.verifyVendoredMermaid(repo);

  assert.strictEqual(vendor.ok, false);
  assert.ok(vendor.problems[0].includes("恰好有一个"), vendor.problems);
});

test("a missing vendor directory is refused", function () {
  const vendor = build.verifyVendoredMermaid(tempDirectory());

  assert.strictEqual(vendor.ok, false);
  assert.ok(vendor.problems[0].includes("renderer/vendor/mermaid"), vendor.problems);
});

test("staging verification reports what is missing", function () {
  const repo = fixtureRepo();
  const vendor = build.verifyVendoredMermaid(repo);
  const dist = tempDirectory();
  const staging = build.prepareStaging(dist);
  assert.strictEqual(fs.existsSync(staging), true);

  const problems = build.verifyStaging(staging, vendor);

  assert.ok(problems.length >= 5, JSON.stringify(problems));
  assert.ok(problems.every((item) => item.includes("staging 缺少文件")), problems);
});

test("staging verification refuses a staged runtime that differs from the vendor", function () {
  const repo = fixtureRepo();
  const vendor = build.verifyVendoredMermaid(repo);
  const dist = tempDirectory();
  const staging = build.prepareStaging(dist);
  fs.writeFileSync(path.join(staging, "renderer.cjs"), "// bundle\n", "utf8");
  fs.mkdirSync(path.join(staging, "katex", "fonts"), { recursive: true });
  fs.writeFileSync(path.join(staging, "katex", "katex.min.css"), "a{}\n", "utf8");
  fs.writeFileSync(path.join(staging, "katex", "fonts", "KaTeX_Main-Regular.woff2"), "x", "utf8");
  fs.mkdirSync(path.join(staging, "mermaid"), { recursive: true });
  fs.writeFileSync(path.join(staging, "mermaid", "mermaid.min.js"), "// not the artifact\n", "utf8");
  fs.writeFileSync(path.join(staging, "mermaid", "metadata.json"), "{}\n", "utf8");

  const problems = build.verifyStaging(staging, vendor);

  assert.deepStrictEqual(problems, ["staging 里的 runtime 与 vendored 产物不一致（SHA-256 不同）"]);
});

test("replacement only touches managed names and drops stale files", function () {
  const repo = fixtureRepo();
  const vendor = build.verifyVendoredMermaid(repo);
  const dist = tempDirectory();
  fs.mkdirSync(path.join(dist, "mermaid"), { recursive: true });
  fs.writeFileSync(path.join(dist, "renderer.cjs"), "// old bundle\n", "utf8");
  fs.writeFileSync(path.join(dist, "mermaid", "stale-runtime.js"), "// from an older version\n", "utf8");
  fs.writeFileSync(path.join(dist, "keep-me.txt"), "user file\n", "utf8");

  const staging = build.prepareStaging(dist);
  fs.writeFileSync(path.join(staging, "renderer.cjs"), "// new bundle\n", "utf8");
  fs.mkdirSync(path.join(staging, "katex"), { recursive: true });
  fs.writeFileSync(path.join(staging, "katex", "katex.min.css"), "a{}\n", "utf8");
  build.copyMermaidRuntime(vendor, path.join(staging, "mermaid"));

  build.replaceManagedAssets(dist, staging);

  assert.strictEqual(fs.readFileSync(path.join(dist, "renderer.cjs"), "utf8"), "// new bundle\n");
  assert.strictEqual(fs.existsSync(path.join(dist, "mermaid", "stale-runtime.js")), false);
  assert.strictEqual(
    fs.readFileSync(path.join(dist, "mermaid", "mermaid.min.js"), "utf8"),
    fs.readFileSync(vendor.artifactPath, "utf8"),
  );
  assert.strictEqual(fs.readFileSync(path.join(dist, "keep-me.txt"), "utf8"), "user file\n");
  assert.strictEqual(fs.existsSync(path.join(dist, ".staging")), false);
});
