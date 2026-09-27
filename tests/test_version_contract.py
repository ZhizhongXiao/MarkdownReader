"""Phase 9B1: the application version has exactly one runtime source.

`pyproject.toml` states the release version, but it is not part of the packaged payload
(`packaging/MarkdownReader.spec` ships the reader, not the build metadata), so the frozen
application cannot read it -- and `importlib.metadata` cannot help either, because this
repository declares itself not installable as a package. The About panel therefore needs
a runtime constant, and a contract that keeps that constant equal to the declared version:
without it the two drift silently and About starts lying about which build is running.

The import lives inside the tests on purpose. A missing module must show up as a failing
contract, not as a collection error that hides what is missing.
"""

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.api import BridgeApi  # noqa: E402


def _declared_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_the_runtime_version_equals_the_declared_release_version():
    """一个版本，两处声明：pyproject 是发布声明，core.version 是运行时事实。"""
    from core import version

    assert version.__version__ == _declared_version()


def test_about_reports_the_runtime_version():
    """About 显示的是那个唯一来源，而不是页面里写死的字符串。"""
    from core import version

    assert BridgeApi().get_about_info()["version"] == version.__version__


def test_the_version_file_is_the_only_place_a_version_is_spelled_out():
    """版本不得在运行时再写第二遍：只有 `core/version.py` 允许出现版本字面量。"""
    literal = '"' + _declared_version() + '"'
    for relative in (
        "gui/api.py",
        "gui/app.py",
        "core/config.py",
        "core/paths.py",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert literal not in text, relative + " must not restate the version; import core.version"
