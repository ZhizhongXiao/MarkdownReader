"""MarkdownReader logging configuration.

Uses Python's built-in logging module. Verbosity is decided by the caller
through setup_logging(); no command-line switch is involved.

A packaged build runs windowed, so a stream handler alone would leave a startup
failure with nowhere to appear. The log therefore also goes to a file, inside the
runtime directory of the user's data (Phase 10) -- see `core/paths.py`, which owns
where that is.
"""

import logging
import os

from core import paths

# Set once the file log has been closed for good. The removal flow closes it while it accepts
# the request (AGENTS section 23: no configuration or log writes after the confirmation), and
# from then on nothing may open the file again: a log that reappears after "remove my data"
# would be a promise the user cannot check.
_file_logging_closed = False


def setup_logging(verbose: bool = False) -> None:
    """Configure the root logger.

    Args:
        verbose: If True, set level to DEBUG. Otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if not _file_logging_closed:
        try:
            # Creating the directory is this function's job: `core.paths` resolves locations
            # without side effects, and an install whose data directory has not been created yet
            # still deserves its log.
            os.makedirs(paths.runtime_root(), exist_ok=True)
            handlers.append(logging.FileHandler(paths.log_path(), encoding="utf-8"))
        except OSError:
            # A read-only location must not keep the application from starting.
            pass
    logging.basicConfig(
        level=level,
        format="%(levelname)-7s: %(message)s",
        handlers=handlers,
        force=True,
    )


def close_file_logging() -> str | None:
    """Detach and close the file handler, and keep the logger from opening it again.

    Returns the path that was closed, or None when there was nothing left to close, so the call
    is idempotent: the removal path may run it even if something else already did.

    Closing the file is what makes "no log writes after the confirmation" true, and it happens
    before the window is destroyed rather than after: the WebView2 profile and the log both live
    in `runtime/`, and only a closed handler guarantees the log is not rewritten underneath the
    deletion that follows.
    """
    global _file_logging_closed
    root = logging.getLogger()
    closed: str | None = None
    for handler in root.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            root.removeHandler(handler)
            handler.close()
            closed = str(handler.baseFilename)
    _file_logging_closed = True
    return closed
