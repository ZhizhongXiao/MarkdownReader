"""Generate samples/demo.html from samples/demo.md for manual inspection.

The generated HTML is intentionally not tracked by Git (see .gitignore); it is
only a local artifact used to eyeball template and styling changes.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INPUT = REPO_ROOT / "samples" / "demo.md"
DEFAULT_OUTPUT = REPO_ROOT / "samples" / "demo.html"


def generate_demo(
    output: Path = DEFAULT_OUTPUT,
    template: str = "modern",
    input_path: Path = DEFAULT_INPUT,
) -> Path:
    """Render the demo Markdown to a standalone HTML file.

    Args:
        output: Destination HTML path.
        template: Template id resolved through the template chain.
        input_path: Source Markdown path.

    Returns:
        The path that was written.

    Raises:
        RuntimeError: If the conversion produced no output file.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from core.converter import process_single

    cfg = {"template": template, "numbering": False, "overwrite": True}
    result = process_single(str(input_path), str(output), cfg)
    if result is None:
        raise RuntimeError("demo generation failed: %s" % input_path)
    return Path(result)


def main(argv: list[str] | None = None) -> int:
    """Generate the demo file and print the written path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--template", default="modern")
    args = parser.parse_args(argv)

    print(generate_demo(output=args.output, template=args.template))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
