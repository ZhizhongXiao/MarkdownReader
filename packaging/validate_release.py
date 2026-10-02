"""Validate a built release the way a user receives it.

This checks the release contract, not the build log:

  * the executable exists and is large enough to be carrying the runtime
  * a onedir release carries Node, the renderer and the reader assets beside the EXE
  * a onefile release starts and survives, which proves the frozen startup check
    found its bundled Node: main() exits when it cannot
  * the local path used here has Chinese characters and spaces, the same shape a
    localized Windows profile produces
  * validation never runs the candidate in place: the onedir tree is validated as a sandbox
    copy, and the onefile run gets a throwaway LOCALAPPDATA/APPDATA. A finished build keeps
    user data beside itself (onedir) or in the developer profile (onefile), so running it
    where it stands would write into the very tree that is about to be packaged

Usage:
    python packaging/validate_release.py --mode onefile|onedir|both
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RUNTIME_FILES = (
    ("node", "node.exe"),
    ("node_renderer", "render.js"),
    ("node_renderer", "node_modules"),
    ("renderer", "dist", "renderer.cjs"),
    ("renderer", "dist", "katex"),
    ("renderer", "dist", "mermaid"),
    ("viewer", "viewer.html"),
    ("viewer", "css", "layout.css"),
    ("viewer", "css", "print.css"),
    ("viewer", "js", "manifest.json"),
    ("themes", "builtin", "base", "theme.css"),
    ("themes", "builtin", "modern", "theme.css"),
    ("themes", "builtin", "office", "theme.css"),
    ("themes", "builtin", "vscode", "theme.css"),
    ("themes", "template", "metadata.json"),
    ("themes", "template", "variables.css"),
    # Phase 12 GUI closeout: the template grew a decoration hook, and `metadata.json` declares it,
    # so a package that lost the file would ship a template that cannot be imported.
    ("themes", "template", "decorations.css"),
    ("templates", "index", "index.js"),
    ("gui", "assets", "index.html"),
)


def report(ok, text):
    print(("  [ok]   " if ok else "  [FAIL] ") + text)
    return ok


def launch_and_survive(exe: Path, wait: int, env: dict | None = None) -> bool:
    """Start the application and see whether it is still alive after $wait seconds.

    `env` replaces the child environment when given. A onefile build keeps its user data in
    `%LOCALAPPDATA%/MarkdownReader`, so `check_onefile` hands it a throwaway profile: inheriting
    the real environment would add a log and a WebView2 profile to the machine that builds the
    release (Phase 12A-2).
    """
    workdir = Path(tempfile.mkdtemp(prefix="MarkdownReader 发布 校验 "))
    process = subprocess.Popen([str(exe)], cwd=str(workdir), env=env)
    try:
        time.sleep(wait)
        return process.poll() is None
    finally:
        # A onefile build starts a bootloader which spawns the real process, and the
        # child keeps the executable open after the parent is gone, so the next build
        # fails with a permission error. The tree is therefore killed while the
        # parent is still alive: Windows cannot walk the tree of a dead process.
        if process.poll() is None and os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
            )
            time.sleep(2)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        if os.name == "nt":
            time.sleep(1)
        shutil.rmtree(workdir, ignore_errors=True)


def sandbox_copy(source: Path) -> Path:
    """Copy a candidate tree so a validation run cannot touch the original.

    An onedir build keeps its user data in `<application_dir>/data`, inside the very tree
    `release_freeze.package_artifacts` archives afterwards. Validating the copy keeps the
    candidate pristine; the caller removes the sandbox when it is done (Phase 12A-2).
    """
    sandbox = Path(tempfile.mkdtemp(prefix="MarkdownReader 发布 沙箱 "))
    target = sandbox / source.name
    shutil.copytree(source, target)
    return target


def onefile_environment() -> dict:
    """Return an environment whose profile roots are throwaway directories.

    A onefile build asks `%LOCALAPPDATA%` (falling back to `%APPDATA%`) for its user data root,
    so both are redirected: validation must not add a log and a WebView2 profile to the machine
    that builds the release.
    """
    profile = tempfile.mkdtemp(prefix="MarkdownReader 发布 profile ")
    return dict(os.environ, LOCALAPPDATA=profile, APPDATA=profile)


def check_onefile(wait: int) -> bool:
    print("onefile:")
    exe = DIST / "MarkdownReader.exe"
    ok = report(exe.is_file(), "dist/MarkdownReader.exe exists")
    if not ok:
        return False
    ok &= report(exe.stat().st_size > 20 * 1024 * 1024, "carries the runtime rather than a stub")
    environment = onefile_environment()
    try:
        ok &= report(
            launch_and_survive(exe, wait, env=environment),
            "starts and survives with a redirected profile (frozen runtime validated)",
        )
    finally:
        shutil.rmtree(environment["LOCALAPPDATA"], ignore_errors=True)
    return ok


def check_onedir(wait: int) -> bool:
    print("onedir:")
    base = DIST / "MarkdownReader"
    exe = base / "MarkdownReader.exe"
    ok = report(exe.is_file(), "dist/MarkdownReader/MarkdownReader.exe exists")
    if not ok:
        return False
    internal = base / "_internal"
    for parts in RUNTIME_FILES:
        ok &= report((internal.joinpath(*parts)).exists(), "_internal/" + "/".join(parts))
    sandbox = sandbox_copy(base)
    try:
        ok &= report(
            launch_and_survive(sandbox / "MarkdownReader.exe", wait),
            "starts and survives in a sandbox copy (candidate tree stays pristine)",
        )
    finally:
        shutil.rmtree(sandbox.parent, ignore_errors=True)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a built MarkdownReader release.")
    parser.add_argument("--mode", choices=("onefile", "onedir", "both"), default="both")
    parser.add_argument("--wait", type=int, default=25, help="seconds the app must survive")
    parser.add_argument("--dist-dir", default="dist", help="directory containing build artifacts")
    args = parser.parse_args()

    global DIST
    dist_dir = Path(args.dist_dir)
    DIST = (ROOT / dist_dir).resolve() if not dist_dir.is_absolute() else dist_dir.resolve()

    if not DIST.is_dir():
        print(str(DIST) + " is missing: build a release first.")
        return 1

    results = []
    if args.mode in ("onefile", "both"):
        results.append(check_onefile(args.wait))
    if args.mode in ("onedir", "both"):
        results.append(check_onedir(args.wait))

    print("release validation: " + ("PASS" if all(results) else "FAIL"))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
