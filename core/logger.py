"""MarkdownReader logging configuration.

Uses Python's built-in logging module. Verbosity is decided by the caller
through setup_logging(); no command-line switch is involved.
"""

import logging


def setup_logging(verbose: bool = False) -> None:
    """Configure the root logger.

    Args:
        verbose: If True, set level to DEBUG. Otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)-7s: %(message)s",
        handlers=[logging.StreamHandler()],
    )
