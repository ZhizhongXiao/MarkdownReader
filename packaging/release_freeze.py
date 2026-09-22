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
PASS_MARKER = "QA 结论：通过"


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
    ticked = text.count("- [x]")
    passed = PASS_MARKER in text and ticked > 0
    # The marker alone is not enough: a fresh checklist must not pass itself.
    shown = (
        str(record_path.relative_to(ROOT)) if record_path.is_relative_to(ROOT) else str(record_path)
    )
    return report(
        passed,
        shown + " (" + str(ticked) + " steps ticked)",
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


def build() -> bool:
    print("build:")
    if DIST.exists():
        shutil.rmtree(DIST, ignore_errors=True)
    ok = True
    for mode in ("onefile", "onedir"):
        result = run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
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
    lines += [
        "- uv.lock  " + sha256(ROOT / "uv.lock"),
        "- package-lock.json  " + sha256(ROOT / "node_renderer" / "package-lock.json"),
        "- node.exe  " + str(runtime.get("sha256")),
        "",
    ]
    (DIST / ("release-record-" + display + ".md")).write_text(
        chr(10).join(lines) + chr(10), encoding="utf-8"
    )
    sums = DIST / "SHA256SUMS.txt"
    sums.write_text(
        chr(10).join(sha256(a) + "  " + a.name for a in artifacts) + chr(10), encoding="utf-8"
    )
    print("wrote dist/release-record-" + display + ".md and dist/SHA256SUMS.txt")


def create_tag(display: str) -> bool:
    print("tag:")
    name = "v" + display
    if run(["git", "tag", "--list", name]).stdout.strip():
        return report(True, name + " already exists")
    ok = report(
        run(["git", "tag", "-a", name, "-m", "MarkdownReader " + display]).returncode == 0,
        "created " + name,
    )
    if ok:
        ok &= report(run(["git", "push", "origin", name]).returncode == 0, "pushed " + name)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze a MarkdownReader release.")
    parser.add_argument(
        "--check-only", action="store_true", help="verify the release evidence only"
    )
    parser.add_argument("--qa-record", default=str(ROOT / "docs" / "QA-CHECKLIST.md"))
    parser.add_argument("--tag", action="store_true", help="create and push the release tag")
    args = parser.parse_args()

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
