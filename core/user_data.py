"""Removing everything MarkdownReader keeps for the current user -- Phase 11.

Two questions live here and nowhere else:

* *what* user data is: the three owned roots plus the legacy configuration residue, each one
  resolved by `core.paths` or by `core.config`'s legacy resolver -- never by a second copy of
  the frozen-layout logic (AGENTS section 24);
* *how* it goes away: bounded retries for a file lock that is still being released, and a
  report that names every path it could not remove instead of claiming success.

It deliberately knows no GUI, no window and no shutdown: the bridge ends the session, and the
application calls this only after `webview.start()` returned, when the WebView2 profile and the
log file are no longer held open.
"""

import logging
import os
import shutil
import time
from collections.abc import Callable

from core import config, paths

_logger = logging.getLogger(__name__)

# The removal runs after the window is gone, so a lock is usually released within a moment. The
# bound is what turns a permanent failure into a reported one instead of a hang.
RETRY_DEADLINE_SECONDS = 2.0
RETRY_INTERVAL_SECONDS = 0.2

# The three facts the confirmation shows. Every path comes from `core.paths`, so the promise the
# page makes and the deletion the application performs cannot drift apart.
ITEM_RESOLVERS: tuple[tuple[str, str, Callable[[], str]], ...] = (
    ("config", "配置", paths.config_path),
    ("external-themes", "外置主题", paths.assets_root),
    ("runtime", "runtime 数据", paths.runtime_root),
)


def removal_available() -> bool:
    """Return True only for onefile.

    onedir already owns its directory -- "delete the folder and the removal is complete" -- and
    source is a working tree. Only onefile leaves data behind that a user cannot remove by
    deleting the program itself.
    """
    return paths.is_frozen() and not paths.is_onedir()


def removal_items() -> list[dict]:
    """Return the facts the confirmation lists, in the order the page shows them."""
    return [
        {"key": key, "label": label, "path": resolve()}
        for key, label, resolve in ITEM_RESOLVERS
    ]


def removal_targets() -> list[str]:
    """Return every path the removal deletes, with the legacy residue last.

    The user data root is deliberately absent: it is only removed once it is empty, so it must
    never be handed to a recursive delete.
    """
    return [
        paths.profile_root(),
        paths.assets_root(),
        paths.runtime_root(),
        config.legacy_config_path(),
    ]


def remove_user_data() -> dict:
    """Delete the user data and report what actually happened.

    Missing targets are no-ops. A path that cannot be removed is named in `failed` and makes
    `ok` false -- including the user data root, because Phase 11's acceptance is "the root is
    gone or empty", and a root kept alive by an unrecognised leftover is neither.
    The guard is the first thing here on purpose: onefile-only is this module's precondition, not
    something a caller is trusted to check. A source tree or an onedir install must be left alone
    even when the request arrives directly.
    """
    if not removal_available():
        _logger.warning("当前布局不提供用户数据移除，未做任何删除：%s", paths.user_data_root())
        return {
            "ok": False,
            "removed": [],
            "failed": [],
            "user_data_root_removed": False,
            "error": "只有 onefile 构建提供用户数据移除。",
        }

    removed: list[str] = []
    failed: list[dict] = []

    for target in removal_targets():
        if not os.path.exists(target):
            continue
        try:
            _delete(target)
        except OSError as error:
            failed.append({"path": target, "error": str(error)})
        else:
            removed.append(target)

    root = paths.user_data_root()
    root_removed = False
    if os.path.isdir(root):
        try:
            _retry(os.rmdir, root)
        except OSError as error:
            failed.append({"path": root, "error": str(error)})
        else:
            root_removed = True

    report = {
        "ok": not failed,
        "removed": removed,
        "failed": failed,
        "user_data_root_removed": root_removed,
    }
    if report["ok"]:
        _logger.info("用户数据已移除：%s", root)
    else:
        _logger.warning("用户数据未能完全移除：%s", failed)
    return report


def _delete(target: str) -> None:
    """Remove one target, whichever kind it is."""
    if os.path.isdir(target) and not os.path.islink(target):
        _retry(shutil.rmtree, target)
        return
    _retry(os.remove, target)


def _retry(operation: Callable[[str], object], target: str) -> None:
    """Run one deletion, retrying a refusal until the deadline runs out."""
    deadline = time.monotonic() + RETRY_DEADLINE_SECONDS
    while True:
        try:
            operation(target)
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(RETRY_INTERVAL_SECONDS)
        else:
            return
