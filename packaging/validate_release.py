"""Validate a built release the way a user receives it.

This checks the release contract, not the build log:

  * the executable exists and is large enough to be carrying the runtime
  * a onedir release carries Node, the renderer and the reader assets beside the EXE
  * a onefile release starts and survives, which proves the frozen startup check
    found its bundled Node: main() exits when it cannot
  * the local path used here has Chinese characters and spaces, the same shape a
    localized Windows profile produces

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
    ("templates", "index", "index.js"),
    ("gui", "assets", "index.html"),
)


def report(ok, text):
    print(("  [ok]   " if ok else "  [FAIL] ") + text)
    return ok


def launch_and_survive(exe: Path, wait: int) -> bool:
    """Start the application and see whether it is still alive after $wait seconds."""
    workdir = Path(tempfile.mkdtemp(prefix="MarkdownReader 发布 校验 "))
    process = subprocess.Popen([str(exe)], cwd=str(workdir))
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


def check_onefile(wait: int) -> bool:
    print("onefile:")
    exe = DIST / "MarkdownReader.exe"
    ok = report(exe.is_file(), "dist/MarkdownReader.exe exists")
    if not ok:
        return False
    ok &= report(exe.stat().st_size > 20 * 1024 * 1024, "carries the runtime rather than a stub")
    ok &= report(launch_and_survive(exe, wait), "starts and survives (frozen runtime validated)")
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
    ok &= report(launch_and_survive(exe, wait), "starts and survives (frozen runtime validated)")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a built MarkdownReader release.")
    parser.add_argument("--mode", choices=("onefile", "onedir", "both"), default="both")
    parser.add_argument("--wait", type=int, default=25, help="seconds the app must survive")
    args = parser.parse_args()

    if not DIST.is_dir():
        print("dist/ is missing: build a release first.")
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
