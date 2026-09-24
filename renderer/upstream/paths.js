"use strict";

/**
 * pinned vscode-office 的位置、被复用的上游源文件清单，以及 upstream provenance 校验。
 *
 * 事实源（Phase 2 定义，这里不重新定义一套）：
 *   - superproject 的 submodule **gitlink** 是 pinned commit 的权威来源；
 *   - upstream/pin.json 是 metadata / integration evidence manifest；
 *   - checkout HEAD 必须等于 gitlink，且 pin.json 登记的 commit 与之一致。
 *
 * build、entry --info 与测试共用这里的检查，不各自实现一套，也不复制 Phase 2 的 PowerShell updater。
 * 检查只用只读 git 命令（ls-files -s / rev-parse），**不修改任何 Git 状态**：绝不 checkout / reset。
 */

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const UPSTREAM_RELATIVE = "upstream/vscode-office";

// 相对 upstream 根目录，与 create_renderer.js 里的字面量 require 一一对应。
const REUSED_SOURCES = [
  "src/service/markdown/ext/markdown-it-obsidian.js",
  "src/service/markdown/ext/markdown-it-katex.js",
];

const RECOVERY_COMMAND = "git submodule update --init --recursive";
const UPDATE_COMMAND = "pwsh tools/update_vscode_office.ps1 -Update <ref>";

function resolveLayout(repoRoot) {
  const root = repoRoot ? path.resolve(repoRoot) : REPO_ROOT;
  return {
    repoRoot: root,
    upstreamRoot: path.join(root, ...UPSTREAM_RELATIVE.split("/")),
    pinManifest: path.join(root, "upstream", "pin.json"),
    gitlinkPath: UPSTREAM_RELATIVE,
  };
}

const DEFAULT_LAYOUT = resolveLayout();

function runGit(args, cwd) {
  const result = spawnSync("git", args, { cwd: cwd, encoding: "utf8" });
  if (result.error) {
    return { ok: false, error: "无法运行 git：" + String(result.error.message || result.error) };
  }
  if (result.status !== 0) {
    const detail = String(result.stderr || "").trim();
    return { ok: false, error: detail || "git 退出码 " + result.status };
  }
  return { ok: true, stdout: String(result.stdout || "").trim() };
}

function readPinManifest(layout) {
  const target = layout || DEFAULT_LAYOUT;
  try {
    const parsed = JSON.parse(fs.readFileSync(target.pinManifest, "utf8"));
    return { commit: String(parsed.pinned_commit || ""), manifest: parsed, error: "" };
  } catch (error) {
    return { commit: "", manifest: null, error: String(error.message || error) };
  }
}

function readGitlink(layout) {
  const target = layout || DEFAULT_LAYOUT;
  const result = runGit(["ls-files", "-s", target.gitlinkPath], target.repoRoot);
  if (!result.ok) {
    return { mode: "", commit: "", error: result.error };
  }
  const parts = result.stdout.split(/\s+/);
  if (parts.length < 4) {
    return { mode: "", commit: "", error: "gitlink 未记录在 superproject 索引中" };
  }
  return { mode: parts[0], commit: parts[1], error: "" };
}

function readCheckoutCommit(layout) {
  const target = layout || DEFAULT_LAYOUT;
  const result = runGit(["rev-parse", "HEAD"], target.upstreamRoot);
  if (!result.ok) {
    return { commit: "", error: result.error };
  }
  return { commit: result.stdout, error: "" };
}

function readWorktreeStatus(layout) {
  const target = layout || DEFAULT_LAYOUT;
  const result = runGit(["status", "--porcelain"], target.upstreamRoot);
  if (!result.ok) {
    return { clean: false, changes: [], error: result.error };
  }
  const changes = result.stdout ? result.stdout.split(/\r?\n/).filter(Boolean) : [];
  return { clean: changes.length === 0, changes: changes, error: "" };
}

function checkProvenance(options) {
  const layout = resolveLayout(options && options.repoRoot);
  const pin = readPinManifest(layout);
  const gitlink = readGitlink(layout);
  const checkout = readCheckoutCommit(layout);
  const worktree = readWorktreeStatus(layout);
  const problems = [];

  if (!pin.commit) {
    problems.push("upstream/pin.json 缺失或没有 pinned_commit：" + (pin.error || ""));
  }
  if (!gitlink.commit) {
    problems.push("superproject 里没有 " + layout.gitlinkPath + " 的 gitlink：" + (gitlink.error || ""));
  } else if (gitlink.mode !== "160000") {
    problems.push("gitlink 模式不是 160000，而是 " + gitlink.mode);
  }
  if (!checkout.commit) {
    problems.push("无法读取 upstream checkout HEAD：" + (checkout.error || ""));
  }
  if (pin.commit && gitlink.commit && pin.commit !== gitlink.commit) {
    problems.push("pin manifest(" + pin.commit + ") 与 authoritative gitlink(" + gitlink.commit + ") 不一致");
  }
  if (gitlink.commit && checkout.commit && gitlink.commit !== checkout.commit) {
    problems.push("upstream checkout(" + checkout.commit + ") 不等于 pinned gitlink(" + gitlink.commit + ")");
  }

  if (!worktree.clean) {
    const summary = worktree.changes.slice(0, 5).join(" | ");
    problems.push(
      "upstream working tree is dirty（" + worktree.changes.length + " 项改动）：" + summary +
        (worktree.changes.length > 5 ? " …" : ""),
    );
  }

  return {
    ok: problems.length === 0,
    repo_root: layout.repoRoot,
    upstream_root: layout.upstreamRoot,
    pinned_commit: pin.commit,
    gitlink_commit: gitlink.commit,
    checkout_commit: checkout.commit,
    worktree_clean: worktree.clean,
    worktree_changes: worktree.changes,
    problems: problems,
    guidance: problems.length
      ? "请恢复 pinned 状态：" + RECOVERY_COMMAND + " 并检查 git -C " + UPSTREAM_RELATIVE + " status" +
        "；若这是有意的 upstream 更新，请先完成 Phase 2 流程（" + UPDATE_COMMAND + " 并同步 upstream/pin.json）。" +
        "本检查只验证、不修复：不会 restore / reset / checkout / 删除任何文件。"
      : "",
  };
}

function missingSources(layout) {
  const target = layout || DEFAULT_LAYOUT;
  return REUSED_SOURCES.filter(function (relative) {
    return !fs.existsSync(path.join(target.upstreamRoot, ...relative.split("/")));
  });
}

function pinnedCommit(options) {
  return readPinManifest(resolveLayout(options && options.repoRoot)).commit;
}

function describe(options) {
  const layout = resolveLayout(options && options.repoRoot);
  const provenance = checkProvenance(options);
  return {
    upstream_root: layout.upstreamRoot,
    pinned_commit: provenance.pinned_commit,
    gitlink_commit: provenance.gitlink_commit,
    checkout_commit: provenance.checkout_commit,
    worktree_clean: provenance.worktree_clean,
    worktree_changes: provenance.worktree_changes,
    provenance_ok: provenance.ok,
    provenance_problems: provenance.problems,
    reused_sources: REUSED_SOURCES.slice(),
    missing_sources: missingSources(layout),
  };
}

module.exports = {
  REPO_ROOT: REPO_ROOT,
  UPSTREAM_RELATIVE: UPSTREAM_RELATIVE,
  REUSED_SOURCES: REUSED_SOURCES,
  RECOVERY_COMMAND: RECOVERY_COMMAND,
  resolveLayout: resolveLayout,
  readPinManifest: readPinManifest,
  readGitlink: readGitlink,
  readCheckoutCommit: readCheckoutCommit,
  readWorktreeStatus: readWorktreeStatus,
  checkProvenance: checkProvenance,
  missingSources: missingSources,
  pinnedCommit: pinnedCommit,
  describe: describe,
};
