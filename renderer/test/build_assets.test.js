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

const OLD_BUNDLE = "// old bundle\n";
const NEW_BUNDLE = "// new bundle\n";

function writeTree(root, files) {
  for (const relative of Object.keys(files)) {
    const target = path.join(root, ...relative.split("/"));
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, files[relative], "utf8");
  }
}

function readTree(root, files) {
  const contents = {};
  for (const relative of files) {
    const target = path.join(root, ...relative.split("/"));
    contents[relative] = fs.existsSync(target) ? fs.readFileSync(target, "utf8") : null;
  }
  return contents;
}

const OLD_SET = {
  "renderer.cjs": OLD_BUNDLE,
  "katex/katex.min.css": "old-katex",
  "mermaid/mermaid.min.js": "old-mermaid",
  "keep-me.txt": "user file",
};
const NEW_SET = {
  "renderer.cjs": NEW_BUNDLE,
  "katex/katex.min.css": "new-katex",
  "mermaid/mermaid.min.js": "new-mermaid",
};
const STALE = "mermaid/stale-runtime.js";

/** 一个已发布过的 dist（旧 managed set + 无关文件 + 一份 stale 残留）与一份完整的 staging。 */
function stagedFixture() {
  const dist = tempDirectory();
  writeTree(dist, OLD_SET);
  writeTree(dist, { [STALE]: "// from an older version\n" });
  const staging = build.prepareStaging(dist);
  writeTree(staging, NEW_SET);
  return { dist: dist, staging: staging };
}

/**
 * 确定性失败注入：默认实现仍是真实 fs，只在指定序号（或指定目标）的调用上抛错。
 * 不依赖文件锁 / 磁盘空间 / 权限这类随机失败。
 */
function failingOps(predicate) {
  const calls = { rename: 0, rm: 0 };
  return {
    calls: calls,
    exists: build.DEFAULT_OPS.exists,
    readdir: build.DEFAULT_OPS.readdir,
    mkdir: build.DEFAULT_OPS.mkdir,
    rm: function (target) {
      calls.rm += 1;
      if (predicate.rm && predicate.rm(target, calls.rm)) {
        throw new Error("injected rm failure");
      }
      return build.DEFAULT_OPS.rm(target);
    },
    rename: function (from, to) {
      calls.rename += 1;
      if (predicate.rename && predicate.rename(calls.rename, from, to)) {
        throw new Error("injected rename failure");
      }
      return build.DEFAULT_OPS.rename(from, to);
    },
  };
}

function assertNoLeftovers(dist) {
  assert.strictEqual(fs.existsSync(path.join(dist, ".staging")), false, ".staging 不得残留");
  assert.strictEqual(fs.existsSync(path.join(dist, ".backup")), false, ".backup 不得残留");
}

function assertOldSetRestored(dist) {
  assert.deepStrictEqual(readTree(dist, Object.keys(OLD_SET)), OLD_SET);
  assert.strictEqual(fs.readFileSync(path.join(dist, STALE), "utf8"), "// from an older version\n");
}

test("a successful replacement installs the new set, drops stale files and keeps unrelated files", function () {
  const fixture = stagedFixture();

  const published = build.publishManagedAssets(fixture.dist, fixture.staging);

  assert.deepStrictEqual(published.installed.slice().sort(), [
    "katex",
    "mermaid",
    "renderer.cjs",
  ]);
  assert.deepStrictEqual(readTree(fixture.dist, Object.keys(NEW_SET)), NEW_SET);
  assert.strictEqual(fs.existsSync(path.join(fixture.dist, STALE)), false, "旧版本 stale 文件必须消失");
  assert.strictEqual(fs.readFileSync(path.join(fixture.dist, "keep-me.txt"), "utf8"), "user file");
  assertNoLeftovers(fixture.dist);
});

test("a failure while moving the old set into backup restores it completely", function () {
  const fixture = stagedFixture();
  const ops = failingOps({ rename: (call) => call === 2 });

  assert.throws(() => build.publishManagedAssets(fixture.dist, fixture.staging, ops), /已恢复旧 managed set/);

  assertOldSetRestored(fixture.dist);
  assertNoLeftovers(fixture.dist);
});

test("a failure on the first install restores the old set completely", function () {
  const fixture = stagedFixture();
  const ops = failingOps({ rename: (call) => call === 4 });

  assert.throws(() => build.publishManagedAssets(fixture.dist, fixture.staging, ops), /已恢复旧 managed set/);

  assertOldSetRestored(fixture.dist);
  assertNoLeftovers(fixture.dist);
});

test("a failure after a partial install restores the old set completely", function () {
  const fixture = stagedFixture();
  const ops = failingOps({ rename: (call) => call === 5 });

  assert.throws(() => build.publishManagedAssets(fixture.dist, fixture.staging, ops), /已恢复旧 managed set/);

  assertOldSetRestored(fixture.dist);
  assertNoLeftovers(fixture.dist);
});

test("a rollback that itself fails keeps .backup and says so instead of pretending", function () {
  const fixture = stagedFixture();
  const managedTargets = build.MANAGED_ASSETS.map((name) => path.join(fixture.dist, name));
  const ops = failingOps({
    // 第 5 次 rename = 第二个资产安装时失败 → 此时已有一个新资产安装成功，rollback 必须删掉它。
    rename: (call) => call === 5,
    // 注入「删不掉已安装的新资产」：rollback 因此无法完成（旧资产放不回原位）。
    rm: (target) => managedTargets.includes(target),
  });

  assert.throws(
    () => build.publishManagedAssets(fixture.dist, fixture.staging, ops),
    /rollback 未完成.*\.backup/s,
  );

  const backup = path.join(fixture.dist, ".backup");
  assert.strictEqual(fs.existsSync(backup), true, "rollback 未完成时必须保留 backup（不假装恢复成功）");
  assert.strictEqual(
    fs.existsSync(path.join(fixture.dist, ".staging")),
    false,
    "staging 无论回滚成败都必须清理",
  );
});

test("withStaging removes the staging directory when the work throws", async function () {
  const dist = tempDirectory();

  await assert.rejects(
    build.withStaging(dist, async function (staging) {
      fs.writeFileSync(path.join(staging, "partial-artifact"), "x", "utf8");
      throw new Error("copy failed");
    }),
    /copy failed/,
  );

  assert.strictEqual(fs.existsSync(path.join(dist, ".staging")), false, ".staging 不得残留");
});

test("withStaging removes the staging directory after success", async function () {
  const dist = tempDirectory();

  const result = await build.withStaging(dist, async function (staging) {
    fs.writeFileSync(path.join(staging, "artifact"), "x", "utf8");
    return "done";
  });

  assert.strictEqual(result, "done");
  assert.strictEqual(fs.existsSync(path.join(dist, ".staging")), false);
});

test("a staging phase that fails leaves the published set untouched", async function () {
  const fixture = stagedFixture();
  fs.rmSync(fixture.staging, { recursive: true, force: true });

  await assert.rejects(
    build.withStaging(fixture.dist, async function () {
      throw new Error("esbuild failed");
    }),
    /esbuild failed/,
  );

  assert.deepStrictEqual(readTree(fixture.dist, Object.keys(OLD_SET)), OLD_SET);
  assert.strictEqual(fs.readFileSync(path.join(fixture.dist, STALE), "utf8"), "// from an older version\n");
  assertNoLeftovers(fixture.dist);
});
