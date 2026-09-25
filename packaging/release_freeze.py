"""Release freeze for MarkdownReader (Stage 9.6).

Runs the mechanical part of a release in a fixed order and refuses to continue
when the evidence is missing:

  1. the version is stated consistently in pyproject.toml, the changelog and the
     release note;
  2. the acceptance checklist records a passing result;
  3. dist/ is rebuilt from scratch, onefile and onedir;
  4. packaging/validate_release.py passes for both shapes;
  5. the artefacts are renamed to their release names, SHA256SUMS.txt and a build
     record are written next to them;
  6. only with --tag: an annotated tag is created and pushed.

Usage:
    python packaging/release_freeze.py --check-only
    python packaging/release_freeze.py
    python packaging/release_freeze.py --tag
    python packaging/release_freeze.py --qa-record path/to/record.md
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
# v2 是 production renderer，v1 保留为 rollback：两套依赖都进发布记录。
RENDERER_DIR = ROOT / "renderer"
RENDERER_LOCK = RENDERER_DIR / "package-lock.json"
NODE_RENDERER_LOCK = ROOT / "node_renderer" / "package-lock.json"
PASS_MARKER = "QA 结论：通过"
# The record is written by hand, so a tick may arrive as [X], with spaces inside
# the brackets, or indented. Every shape counts the same. A box holding anything
# other than x stays unticked, so a typo cannot pass for a finished item.
BOX = re.compile(r"^\s*-\s*\[\s*([^\]]*?)\s*\]", re.MULTILINE)


def fail(message: str) -> None:
    print("[FAIL] " + message)
    raise SystemExit(1)


def report(ok: bool, text: str) -> bool:
    print(("  [ok]   " if ok else "  [FAIL] ") + text)
    return ok


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def version_facts() -> dict:
    """Collect the version each consumer states and require them to agree."""
    pyproject = read(ROOT / "pyproject.toml")
    match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    if match is None:
        fail("pyproject.toml 没有 version")
    package_version = match.group(1)
    display = package_version.replace("rc", "-rc") if "rc" in package_version else package_version
    return {"package": package_version, "display": display}


def git(*args) -> str:
    return run(["git", *args]).stdout.strip()


def repository_gate() -> bool:
    """A release must be buildable from the commit it claims to be."""
    print("repository:")
    fetched = run(["git", "fetch", "origin", "main", "--quiet"])
    ok = report(fetched.returncode == 0, "reached origin")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    ok &= report(branch == "main", "on branch main (found " + branch + ")")
    dirty = git("status", "--porcelain")
    ok &= report(
        not dirty,
        "working tree is clean" if not dirty else "working tree has uncommitted changes",
    )
    if dirty:
        print(dirty[:1200])
        print("  commit the release evidence first: the tag must describe the code that was built.")
    head = git("rev-parse", "HEAD")
    remote = git("rev-parse", "origin/main")
    ok &= report(head == remote, "HEAD matches origin/main (" + head[:12] + ")")
    return ok


def version_agreement(facts: dict) -> bool:
    """The same version must appear in every place a consumer reads it."""
    print("version:")
    ok = report(bool(facts["package"]), "pyproject.toml states " + facts["package"])
    changelog = read(ROOT / "docs" / "CHANGELOG.md")
    ok &= report(
        "## [" + facts["display"] + "]" in changelog,
        "docs/CHANGELOG.md has a " + facts["display"] + " section",
    )
    title = read(ROOT / "release-readme.md").splitlines()[0]
    ok &= report(facts["display"] in title, "release-readme.md title states " + facts["display"])
    return ok


def qa_gate(record_path: Path) -> bool:
    """Refuse to build a release nobody accepted on a real machine."""
    print("acceptance:")
    if not record_path.is_file():
        return report(False, "missing acceptance record: " + str(record_path))
    text = read(record_path)
    marks = [match.group(1) for match in BOX.finditer(text)]
    ticked = sum(1 for mark in marks if mark.lower() == "x")
    total = len(marks)
    passed = total > 0 and ticked == total and PASS_MARKER in text
    # The marker alone is not enough: a fresh checklist must not pass itself.
    shown = (
        str(record_path.relative_to(ROOT)) if record_path.is_relative_to(ROOT) else str(record_path)
    )
    return report(
        passed,
        shown + " (" + str(ticked) + "/" + str(total) + " steps ticked)",
    )


def run(command, **kwargs):
    return subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )


def build_renderer() -> bool:
    """Build renderer/dist before packaging; the spec refuses to pack without it.

    renderer/dist is a gitignored build artifact, so "the spec verifies and
    collects it" only works while something produces it -- that is this step. It
    runs once for both packagings, and renderer/build/build.js keeps its own
    staged, verified and rollback-protected replacement contract.
    """
    print("renderer:")
    npm = shutil.which("npm")
    if npm is None:
        return report(False, "npm not on PATH (the v2 renderer payload must be built)")
    for arguments in (["ci"], ["run", "build"]):
        result = subprocess.run(
            [npm, *arguments],
            cwd=str(RENDERER_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if not report(result.returncode == 0, "npm " + " ".join(arguments)):
            print((result.stdout or "")[-1500:])
            print((result.stderr or "")[-1500:])
            return False
    return True


def build() -> bool:
    print("build:")
    if DIST.exists():
        shutil.rmtree(DIST, ignore_errors=True)
    if not build_renderer():
        return False
    ok = True
    for mode in ("onefile", "onedir"):
        result = run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--workpath",
                "packaging/.pyinstaller-build",
                "--distpath",
                "dist",
                "--log-level",
                "WARN",
                "packaging/MarkdownReader.spec",
            ],
            env=dict(os.environ, MR_BUILD_MODE=mode),
        )
        ok &= report(result.returncode == 0, mode + " build")
        if result.returncode != 0:
            print((result.stdout or "")[-1500:])
            print((result.stderr or "")[-1500:])
    return ok


def validate() -> bool:
    print("validate:")
    result = run(
        [sys.executable, "packaging/validate_release.py", "--mode", "both", "--wait", "20"]
    )
    ok = report(result.returncode == 0, "packaging/validate_release.py")
    print(result.stdout)
    return ok


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def package_artifacts(display: str) -> list:
    print("package:")
    artifacts = []
    final_exe = DIST / ("MarkdownReader-" + display + "-win-x64.exe")
    shutil.copy2(DIST / "MarkdownReader.exe", final_exe)
    artifacts.append(final_exe)
    onedir = DIST / "MarkdownReader"
    if onedir.is_dir():
        archive = DIST / ("MarkdownReader-" + display + "-portable-win-x64.zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(onedir.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(DIST))
        artifacts.append(archive)
    for artifact in artifacts:
        report(True, artifact.name + "  " + str(int(artifact.stat().st_size / 1024 / 1024)) + " MB")
    return artifacts


def tool_version(distribution):
    """Return the installed version of a distribution, or unknown."""
    probe = "import importlib.metadata as m; print(m.version(" + repr(distribution) + "))"
    result = run([sys.executable, "-c", probe])
    return (result.stdout or "").strip() or "unknown"


def release_inputs() -> list:
    """Return the (label, sha256) build inputs a release record must carry.

    v2 is the production renderer and v1 stays the rollback path, so both
    renderer dependency sets are recorded: swapping either lockfile without a
    rebuild is a change the record has to show.
    """
    runtime = json.loads(read(ROOT / "packaging" / "node-runtime.json"))
    return [
        ("uv.lock", sha256(ROOT / "uv.lock")),
        ("node_renderer/package-lock.json  (v1 rollback)", sha256(NODE_RENDERER_LOCK)),
        ("renderer/package-lock.json  (v2 production)", sha256(RENDERER_LOCK)),
        ("node.exe", str(runtime.get("sha256"))),
    ]


def write_record(display: str, artifacts: list, with_tag: bool) -> None:
    runtime = json.loads(read(ROOT / "packaging" / "node-runtime.json"))
    commit = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    lines = [
        "# MarkdownReader " + display + " - 构建记录",
        "",
        "- 日期：" + date.today().isoformat(),
        "- Commit：" + commit,
        "- Python：" + sys.version.split()[0],
        "- PyInstaller：" + tool_version("PyInstaller"),
        "- pywebview：" + tool_version("pywebview"),
        "- PyYAML：" + tool_version("PyYAML"),
        "- Node：" + str(runtime.get("version")),
        "- tag：" + (("v" + display) if with_tag else "未打（dry run）"),
        "",
        "## 校验和",
        "",
    ]
    lines += ["- " + a.name + "  " + sha256(a) for a in artifacts]
    lines += ["- " + label + "  " + value for label, value in release_inputs()]
    lines += [""]
    (DIST / ("release-record-" + display + ".md")).write_text(
        chr(10).join(lines) + chr(10), encoding="utf-8"
    )
    sums = DIST / "SHA256SUMS.txt"
    sums.write_text(
        chr(10).join(sha256(a) + "  " + a.name for a in artifacts) + chr(10), encoding="utf-8"
    )
    print("wrote dist/release-record-" + display + ".md and dist/SHA256SUMS.txt")


def create_tag(display: str) -> bool:
    """Create the tag only when it matches HEAD, locally and on the remote."""
    print("tag:")
    name = "v" + display
    head = git("rev-parse", "HEAD")
    local = git("rev-parse", "-q", "--verify", "refs/tags/" + name)
    if local:
        if not report(local == head, name + " points at HEAD (" + local[:12] + ")"):
            print("the tag exists but points elsewhere: delete it deliberately, do not move it")
            return False
    elif not report(
        run(["git", "tag", "-a", name, "-m", "MarkdownReader " + display]).returncode == 0,
        "created " + name,
    ):
        return False

    peeled = "refs/tags/" + name + "^{}"
    remote = git("ls-remote", "--tags", "origin", peeled)
    if not remote:
        # The local tag may exist while an earlier push failed, so the remote
        # is always probed and the push retried instead of reporting success.
        pushed = run(["git", "push", "origin", name])
        if not report(pushed.returncode == 0, "pushed " + name):
            return False
        remote = git("ls-remote", "--tags", "origin", peeled)
    parts = remote.split()
    remote_sha = parts[0] if parts else ""
    return report(
        remote_sha == head,
        "remote " + name + " points at HEAD (" + (remote_sha[:12] or "missing") + ")",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze a MarkdownReader release.")
    parser.add_argument(
        "--check-only", action="store_true", help="verify the release evidence only"
    )
    parser.add_argument("--qa-record", default=str(ROOT / "docs" / "QA-CHECKLIST.md"))
    parser.add_argument("--tag", action="store_true", help="create and push the release tag")
    args = parser.parse_args()

    if not repository_gate():
        print("release freeze: FAIL (repository state)")
        return 1
    facts = version_facts()
    if not version_agreement(facts) or not qa_gate(Path(args.qa_record)):
        print("release freeze: FAIL (evidence missing, nothing built)")
        return 1
    if args.check_only:
        print("release freeze: evidence OK")
        return 0
    if not build() or not validate():
        print("release freeze: FAIL (build or validation)")
        return 1
    artifacts = package_artifacts(facts["display"])
    write_record(facts["display"], artifacts, args.tag)
    if args.tag and not create_tag(facts["display"]):
        print("release freeze: FAIL (tag)")
        return 1
    print("release freeze: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
