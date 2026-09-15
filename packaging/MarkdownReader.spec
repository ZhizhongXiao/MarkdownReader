# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path.cwd()
packaging_dir = project_root / "packaging"
assets_dir = packaging_dir / "assets"


def add_tree(datas, source, target):
    source = Path(source)
    if source.exists():
        datas.append((str(source), target))


datas = []
add_tree(datas, project_root / "gui" / "assets", "gui/assets")
add_tree(datas, project_root / "templates", "templates")
add_tree(datas, project_root / "node_renderer", "node_renderer")

# Optional portable Node.js runtime. Put node.exe under packaging/node before
# building if the release should run without user-installed Node.js.
add_tree(datas, packaging_dir / "node", "node")

icon_file = assets_dir / "MarkdownReader.ico"
splash_file = assets_dir / "MarkdownReader_splash.png"


a = Analysis(
    ["main.py"],
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

exe = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
    a.binaries,
    a.datas,
    [],
    name="MarkdownReader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
