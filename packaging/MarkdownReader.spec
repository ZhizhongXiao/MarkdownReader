# -*- mode: python ; coding: utf-8 -*-

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

# onefile is the primary release shape; onedir starts faster and is friendlier to
# Defender, so the same spec can produce either.
BUILD_MODE = os.environ.get("MR_BUILD_MODE", "onefile").strip().lower()


# PyInstaller resolves the spec relative script names against the spec file, so
# the project root comes from the spec location rather than from the current
# directory: running the build from anywhere must produce the same release.
project_root = Path(SPECPATH).resolve().parent
packaging_dir = project_root / "packaging"
assets_dir = packaging_dir / "assets"


def add_tree(datas, source, target):
    source = Path(source)
    if source.exists():
        datas.append((str(source), target))


# A release must be self-contained. Fail the build here instead of producing an
# EXE that only works on machines which happen to have Node installed.
bundled_node = packaging_dir / "node" / "node.exe"


def require_file(relative):
    """Fail the build when a release-required file is missing."""
    if not (project_root / relative).is_file():
        raise SystemExit("发布资源缺失（文件）：" + relative)


def require_dir(relative):
    """Fail the build when a release-required directory is missing."""
    if not (project_root / relative).is_dir():
        raise SystemExit("发布资源缺失（目录）：" + relative)


def require_node_floor(version):
    """Assert the recorded bundled Node meets the v2 renderer capability floor.

    下限常量只有一处来源（`core/renderer_v2.py`），这里不另造 Node manifest：只给已记录的
    版本加一条「major >= 18」的断言。导入放在函数内，因为这是 PyInstaller 的 spec：
    SPECPATH / Analysis / EXE 等名字由它注入，模块级导入顺序不属于这里关心的事。
    """
    sys.path.insert(0, str(project_root))
    from core.renderer_v2 import MINIMUM_NODE_MAJOR

    major = str(version).strip().lstrip("vV").split(".", 1)[0]
    if not major.isdigit() or int(major) < MINIMUM_NODE_MAJOR:
        raise SystemExit(
            "内置 Node 低于 v2 renderer 的下限 v" + str(MINIMUM_NODE_MAJOR) + "：" + str(version)
        )


# Everything the packaged application reads at runtime. add_tree() below skips
# missing sources on purpose, since the reader assets ship as whole trees, so the
# files that must exist are named here instead: a release either carries all of
# them or it is not produced, because gui/app.py falls back to a placeholder page
# and would otherwise let a broken build start and look healthy.
REQUIRED_FILES = (
    "main.py",
    "gui/assets/index.html",
    "gui/assets/gui.css",
    "gui/assets/gui.js",
    "viewer/viewer.html",
    "viewer/css/layout.css",
    "viewer/css/print.css",
    "viewer/js/manifest.json",
    "themes/builtin/base/theme.css",
    "themes/builtin/base/metadata.json",
    "themes/builtin/modern/theme.css",
    "themes/builtin/modern/metadata.json",
    "themes/builtin/office/theme.css",
    "themes/builtin/office/metadata.json",
    "themes/builtin/vscode/theme.css",
    "themes/builtin/vscode/metadata.json",
    "templates/index/index.html",
    "templates/index/index.js",
    "templates/index/theme.css",
    "node_renderer/render.js",
    "node_renderer/package.json",
    "node_renderer/package-lock.json",
    "renderer/dist/renderer.cjs",
    "renderer/dist/katex/katex.min.css",
    "renderer/dist/mermaid/mermaid.min.js",
    "packaging/node/node.exe",
)
for _relative in REQUIRED_FILES:
    require_file(_relative)

for _relative in (
    "viewer/js",
    "themes/builtin",
    "node_renderer/node_modules",
    "renderer/dist/katex",
    "renderer/dist/mermaid",
    "packaging/node",
):
    require_dir(_relative)

# Validate the renderer for real before building: an empty or incomplete
# node_modules satisfies an existence check while the first conversion fails.
_probe = subprocess.run(
    [str(bundled_node), "--version"],
    capture_output=True,
    text=True,
    timeout=15,
)
if _probe.returncode != 0:
    raise SystemExit("内置 Node 无法运行：packaging/node/node.exe")

# The bundled runtime is a build input like any other: record which one was
# validated, so swapping node.exe is noticed instead of silently shipped.
_runtime_record = project_root / "packaging" / "node-runtime.json"
if not _runtime_record.is_file():
    raise SystemExit("缺少 packaging/node-runtime.json：请先记录内置 Node 的版本与哈希。")
_manifest = json.loads(_runtime_record.read_text(encoding="utf-8"))
_actual_version = (_probe.stdout or "").strip()
_expected_version = str(_manifest.get("version", ""))
if _actual_version != _expected_version:
    raise SystemExit(
        "内置 Node 版本与 packaging/node-runtime.json 不一致："
        + _actual_version + " != " + _expected_version
    )

# 能力下限（Cutover C2）：v2 renderer 需要 Node 18 起。exact-version + SHA-256 门禁照旧，
# 这里只多一条下限断言 —— 记录里的 Node 降级到 18 以下会让 v2 无法工作。
require_node_floor(_expected_version)
_hasher = hashlib.sha256()
with open(bundled_node, "rb") as _stream:
    for _chunk in iter(lambda: _stream.read(1024 * 1024), b""):
        _hasher.update(_chunk)
_expected_sha = str(_manifest.get("sha256", ""))
if _hasher.hexdigest() != _expected_sha:
    raise SystemExit(
        "内置 Node 的 SHA-256 与 packaging/node-runtime.json 不一致。"
    )

_smoke = subprocess.run(
    [
        sys.executable,
        "-c",
        "from core.renderer_node import validate_renderer_runtime; validate_renderer_runtime()",
    ],
    cwd=str(project_root),
    capture_output=True,
    text=True,
)
if _smoke.returncode != 0:
    raise SystemExit(
        "Node 渲染器自检未通过："
        + ((_smoke.stderr or _smoke.stdout or "").strip()[:2000])
    )

# Cutover C4: the release renders with v2 by default, so the build has to prove
# that the renderer/dist about to be packaged works with the node.exe about to be
# packaged -- not that some Node on PATH happens to work.
_v2_smoke_source = (
    "from core import renderer_v2; renderer_v2.validate_v2_runtime("
    + repr(str(bundled_node))
    + ")"
)
_v2_smoke = subprocess.run(
    [sys.executable, "-c", _v2_smoke_source],
    cwd=str(project_root),
    capture_output=True,
    text=True,
)
if _v2_smoke.returncode != 0:
    raise SystemExit(
        "v2 renderer 自检未通过："
        + ((_v2_smoke.stderr or _v2_smoke.stdout or "").strip()[:2000])
    )

datas = []
add_tree(datas, project_root / "gui" / "assets", "gui/assets")
# The reader's assets live in their own roots since Phase 6B: the shell, styles and
# script under viewer/, the themes under themes/builtin/. The batch index page is a
# separate surface and keeps its templates/index/ home.
add_tree(datas, project_root / "viewer", "viewer")
add_tree(datas, project_root / "themes", "themes")
add_tree(datas, project_root / "templates" / "index", "templates/index")
add_tree(datas, project_root / "node_renderer", "node_renderer")

# The v2 renderer payload (Cutover C4): renderer/dist is a gitignored build
# artifact, so packaging/README.md and release_freeze.py own producing it while
# this spec verifies and collects it. Only dist/ ships -- renderer/node_modules,
# renderer/src and renderer/vendor are build-time inputs, not runtime payload.
add_tree(datas, project_root / "renderer" / "dist", "renderer/dist")

# Optional portable Node.js runtime. Put node.exe under packaging/node before
# building if the release should run without user-installed Node.js.
add_tree(datas, packaging_dir / "node", "node")

icon_file = assets_dir / "MarkdownReader.ico"
splash_file = assets_dir / "MarkdownReader_splash.png"


a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=["pyi_splash"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

splash = Splash(
    str(splash_file),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    text_size=12,
    minify_script=True,
    always_on_top=True,
)

exe_kwargs = dict(
    name="MarkdownReader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX compression is off: it is a common false-positive trigger for
    # antivirus engines, and a release that gets quarantined is worse than
    # a larger file.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file) if icon_file.exists() else None,
)

if BUILD_MODE not in ("onefile", "onedir"):
    raise SystemExit(
        "MR_BUILD_MODE 只能是 onefile 或 onedir，收到：" + BUILD_MODE
    )

if BUILD_MODE == "onedir":
    exe = EXE(
        pyz,
        a.scripts,
        splash,
        splash.binaries,
        [],
        exclude_binaries=True,
        **exe_kwargs,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="MarkdownReader",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        splash,
        splash.binaries,
        a.binaries,
        a.datas,
        [],
        **exe_kwargs,
    )
