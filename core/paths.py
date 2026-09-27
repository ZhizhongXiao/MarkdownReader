"""Where MarkdownReader reads and writes -- the one module that knows.

AGENTS section 24: business modules must not judge PyInstaller paths themselves, so
`sys.frozen` and `sys._MEIPASS` are read here and nowhere else under `core/`, `gui/`
or `tools/`. Three layouts exist; all three user-data roots are writable, while the
bundled assets are read-only:

    source   <repo>/.runtime/{profile,assets,runtime}
    onedir   <app>/data/{profile,assets,runtime}
    onefile  %LOCALAPPDATA%/MarkdownReader/{profile,assets,runtime}

Why they differ: onedir already owns a directory, so keeping user data inside it
makes "delete the folder" a complete removal; onefile is a single read-only EXE, so
persistent data has to live under `%LOCALAPPDATA%` and survives moving the EXE.

Phase 7A published this module because external themes need a writable, persistent home
(`assets/themes/external/`). Phase 10 finished the classification: `config.json` lives in
`profile/`, the log and the WebView2 profile live in `runtime/`, and the legacy
configuration beside the executable is only an upgrade input. The "remove user data" flow
is Phase 11.

Everything here is pure: resolving a path never creates a directory.
"""

import os
import sys

_PROJECT_NAME = "MarkdownReader"
CONFIG_FILENAME = "config.json"
LOG_FILENAME = "MarkdownReader.log"
WEBVIEW_DIRNAME = "WebView2"


def source_root() -> str:
    """Return the repository root, which is also the source-mode application dir."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_frozen() -> bool:
    """Return True inside a PyInstaller build (onedir or onefile)."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> str:
    """Return the read-only directory holding the packaged assets."""
    return os.path.abspath(getattr(sys, "_MEIPASS", source_root()))


def application_dir() -> str:
    """Return the EXE directory when frozen, otherwise the repository root."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return source_root()


def is_onedir() -> bool:
    """Return True when the frozen bundle sits beside the EXE.

    onefile extracts itself into a temporary directory, which is never a child of the
    EXE directory; onedir bundles live in a subdirectory of it. Comparing the two
    avoids hardcoding PyInstaller directory names.
    """
    return is_frozen() and os.path.dirname(bundle_root()) == application_dir()


def onefile_root() -> str:
    """Return the persistent root onefile uses for user data.

    `%LOCALAPPDATA%` is the Windows answer; when the variable is missing (a stripped
    environment, or a non-Windows run) this falls back to the conventional
    `~/AppData/Local` location instead of failing, because losing the log directory is
    not a reason to refuse to start.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, _PROJECT_NAME)


def user_data_root() -> str:
    """Return the writable root of profile / assets / runtime."""
    if not is_frozen():
        return os.path.join(source_root(), ".runtime")
    if is_onedir():
        return os.path.join(application_dir(), "data")
    return onefile_root()


def profile_root() -> str:
    """Return the directory holding user preferences (`config.json`)."""
    return os.path.join(user_data_root(), "profile")


def assets_root() -> str:
    """Return the directory holding user assets (installed external themes)."""
    return os.path.join(user_data_root(), "assets")


def runtime_root() -> str:
    """Return the directory for reproducible runtime data (logs, caches)."""
    return os.path.join(user_data_root(), "runtime")


def log_path() -> str:
    """Return the application log file, inside the runtime root.

    Phase 9B found the log sitting in `application_dir()`, which for onefile means "beside the
    EXE -- wherever the user put it" and for onedir a stray file inside a folder that is meant
    to be self-contained. It is runtime data, so it belongs with the rest of it (Phase 10).
    """
    return os.path.join(runtime_root(), LOG_FILENAME)


def webview_storage_root() -> str:
    """Return the WebView2 profile directory, inside the runtime root.

    The engine's profile is runtime data like the log, and its name is an implementation
    detail of the GUI. Keeping it here is what finally makes onedir's "delete the folder and
    the removal is complete" true, while onefile keeps everything under `%LOCALAPPDATA%`.
    """
    return os.path.join(runtime_root(), WEBVIEW_DIRNAME)


def external_themes_root() -> str:
    """Return the directory installed external themes live in.

    Builtin themes are read-only package payload; external themes are user content,
    which is why they never share a directory with `themes/builtin/`.
    """
    return os.path.join(assets_root(), "themes", "external")


def config_path() -> str:
    """Return the intended location of `profile/config.json`."""
    return os.path.join(profile_root(), CONFIG_FILENAME)
