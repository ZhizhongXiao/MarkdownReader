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


def setup_logging(verbose: bool = False) -> None:
    """Configure the root logger.

    Args:
        verbose: If True, set level to DEBUG. Otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]
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
