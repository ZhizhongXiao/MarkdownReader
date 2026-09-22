"""MarkdownReader logging configuration.

Uses Python's built-in logging module. Verbosity is decided by the caller
through setup_logging(); no command-line switch is involved.

A packaged build runs windowed, so a stream handler alone would leave a startup
failure with nowhere to appear. The log therefore also goes to a file next to the
executable, which is also what a bug report needs.
"""

import logging
import os

LOG_FILENAME = "MarkdownReader.log"


def setup_logging(verbose: bool = False) -> None:
    """Configure the root logger.

    Args:
        verbose: If True, set level to DEBUG. Otherwise INFO.
    """
    from core.config import get_application_dir

    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        log_path = os.path.join(get_application_dir(), LOG_FILENAME)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    except OSError:
        # A read-only install directory must not keep the application from starting.
        pass
    logging.basicConfig(
        level=level,
        format="%(levelname)-7s: %(message)s",
        handlers=handlers,
        force=True,
    )
