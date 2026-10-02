"""Phase 12A-2 follow-up: the acceptance guide and the acceptance record must describe one run.

`packaging/qa_prepare.py` writes the operating guide a person follows, and
`docs/QA-CHECKLIST-1.0.0-rc1-v2.md` is the record `release_freeze.py` actually gates on. When
the record was re-baselined for Phase 12A the guide kept its old grouping (C document features,
D reader, E index page) and its old A numbering, so following the guide could not produce the
evidence the gate requires: storage lifecycle, external theme persistence, onefile removal and
legacy migration were simply absent from the operating steps.

The two files are tied together here instead of by prose review:

* same section letters, in the same order;
* the same number of steps per section as there are record items;
* steps numbered contiguously from 1;
* one stable token per record item, which has to appear in the guide step carrying that number;
* the guide names the record that discovery actually selects;
* the old group titles are gone, so the retired manual groups cannot come back by copy-paste.

Tokens are facts an item is about (a control name, a path, a word the user sees), not phrasing:
rewording a sentence keeps the contract, dropping or merging an item breaks it.
"""

import importlib.util
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

CHECKLIST = ROOT / "docs" / "QA-CHECKLIST-1.0.0-rc1-v2.md"
SECTION = re.compile(r"^## ([A-H])[. ]")
# Any checkbox line is one record item, whatever its mark holds: `[ ]`, `[x]`, `[X]`, `[ x ]`
# and even a mistyped `[y]` are all list items. Whether an item *passes* is the release gate's
# business (`release_freeze.qa_gate`), and the structure here must not depend on it -- counting
# only unchecked boxes would turn "QA finished" into a structural red.
CHECKBOX = re.compile(r"^\s*-\s*\[[^\]]*\]", re.MULTILINE)
FLIP = re.compile(r"^(\s*-\s*)\[([^\]]*)\]", re.MULTILINE)
STEP = re.compile(r"^- ([A-H])(\d+)\b")

# One stable token per record item, keyed by (section, item number).
TOKENS = {
    ("A", 1): "onefile",
    ("A", 2): "onedir",
    ("A", 3): "Node/npm",
    ("A", 4): "WebView2",
    ("A", 5): "普通用户",
    ("A", 6): "中文",
    ("A", 7): "renderer.cjs",
    ("B", 1): "Ctrl / Shift",
    ("B", 2): "拖入文件",
    ("B", 3): "单文件转换",
    ("B", 4): "保留目录结构",
    ("B", 5): "索引页",
    ("B", 6): "Mermaid",
    # 重基线（Phase 12 GUI closeout）：B7 从「三套模板各转换一次」改成阅读端主题切换 —— GUI 不再有
    # 内置主题选择器，三套内置主题永远随产物，选择发生在阅读页面里。
    ("B", 7): "主题切换",
    ("C", 1): "profile",
    ("C", 2): "存储信息",
    ("C", 3): "runtime",
    ("C", 4): "改名",
    ("C", 5): "复制",
    ("C", 6): "删除整个应用目录",
    # 重基线（Phase 12 GUI closeout）：D 组从「导出模板 -> 改名 -> 导入」改成
    # 「导入仓库内两个验收标本 -> 预览/携带正交 -> 转换 -> 持久化 -> 卸载 -> 导出-编辑-导入」。
    # 判据未变：每个条目仍必须有一个能执行的向导步骤与之对应。
    ("D", 1): "qa-ornamented",
    ("D", 2): "互不干扰",
    ("D", 3): "内嵌",
    ("D", 4): "重启",
    ("D", 5): "卸载",
    ("D", 6): "导出主题模板",
    ("E", 1): "入口",
    ("E", 2): "5 秒",
    ("E", 3): "空根",
    ("E", 4): "再次启动",
    ("F", 1): "EXE 同级",
    ("F", 2): "不复活",
    ("G", 1): "打印预览",
    ("G", 2): "PDF",
    ("H", 1): "Defender",
}

# The external-theme validator scopes every rule to `html[data-theme-id="<metadata.id>"]`, so a
# recipe that only renames the metadata id produces a theme that cannot be imported. D6 has to
# name both halves of the rename, while staying free of CSS file names: the file list may change
# with the template, the two selector forms may not.
#
# Phase 12 GUI closeout: the export -> edit -> import loop kept its own step (D6) instead of
# sharing D1 with it, because D1 is now the in-repo fixture import.
THEME_RECIPE = (
    "metadata.json",
    "my-theme",
    "qa-theme",
    "data-theme-id",
    "theme-qa-theme",
    "theme-my-theme",
)

# Titles the guide used to carry as manual groups. They are no longer part of the run.
RETIRED = ("C 文档特性", "D 阅读器", "E 索引页")


def _guide_text() -> str:
    """Return the operating guide that `qa_prepare.py` writes for the acceptance run."""
    spec = importlib.util.spec_from_file_location(
        "qa_prepare_under_test", ROOT / "packaging" / "qa_prepare.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.GUIDE


def _split_sections(text: str) -> list:
    """Return (letter, body) for every `## X …` section, in file order."""
    found: list = []
    current = None
    for line in text.splitlines():
        match = SECTION.match(line)
        if match:
            current = (match.group(1), [])
            found.append(current)
        elif current is not None:
            current[1].append(line)
    return [(letter, "\n".join(body)) for letter, body in found]


def _count_items(record_text: str) -> list:
    """Return (letter, item count) per section, counting every checkbox line."""
    return [
        (letter, len(CHECKBOX.findall(body))) for letter, body in _split_sections(record_text)
    ]


def _record_counts() -> list:
    """Return (letter, item count) for the record the gate reads."""
    return _count_items(CHECKLIST.read_text(encoding="utf-8"))


def _guide_counts(guide: str) -> list:
    """Return (letter, step count) per section of the operating guide."""
    return [
        (letter, len(re.findall(r"^- " + letter + r"\d+", body, re.MULTILINE)))
        for letter, body in _split_sections(guide)
    ]


def _flip_states(record_text: str) -> str:
    """Return the record with every checkbox flipped, for state-independence checks."""
    return FLIP.sub(
        lambda match: match.group(1)
        + "["
        + (" " if match.group(2).strip().lower() == "x" else "X")
        + "]",
        record_text,
    )


def _guide_steps(guide: str) -> dict:
    """Return {(letter, number): text} for every numbered step, continuations included."""
    steps: dict = {}
    current = None
    for line in guide.splitlines():
        match = STEP.match(line)
        if match:
            current = (match.group(1), int(match.group(2)))
            steps[current] = line
        elif current is not None and line.strip() and not line.startswith("- "):
            steps[current] += "\n" + line
    return steps


def test_the_guide_covers_the_record_section_by_section() -> None:
    guide = _guide_text()
    expected = _record_counts()
    actual = _guide_counts(guide)

    assert [letter for letter, _ in actual] == [letter for letter, _ in expected], (
        "the guide sections and the record sections no longer line up: "
        + str([letter for letter, _ in actual])
    )
    assert actual == expected, (
        "guide step counts differ from record item counts: " + str(actual) + " vs " + str(expected)
    )


def test_every_step_is_numbered_contiguously() -> None:
    steps = _guide_steps(_guide_text())
    counts = dict(_record_counts())

    for letter, count in counts.items():
        numbers = sorted(number for (step_letter, number) in steps if step_letter == letter)
        assert numbers == list(range(1, count + 1)), (letter, numbers)


def test_each_record_item_has_a_matching_guide_step() -> None:
    steps = _guide_steps(_guide_text())
    missing = []

    for (letter, number), token in TOKENS.items():
        if token not in steps.get((letter, number), ""):
            missing.append(letter + str(number) + " needs " + token)

    assert not missing, "the guide does not cover these record items: " + "; ".join(missing)


def test_no_preview_step_describes_the_full_area_text_fallback() -> None:
    step = _guide_steps(_guide_text()).get(("D", 1), "")

    for expected in ("隐藏整张示意图", "水平、垂直居中", "填满默认预览区域"):
        assert expected in step, "D1 does not describe the no-preview fallback: " + expected


def test_the_guide_names_the_record_discovery_selects() -> None:
    spec = importlib.util.spec_from_file_location(
        "release_freeze_under_test", ROOT / "packaging" / "release_freeze.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    record = module.resolve_qa_record()

    assert record.name in _guide_text(), (
        "the guide points at a different record than the gate reads: " + record.name
    )


def test_the_retired_manual_groups_are_gone() -> None:
    guide = _guide_text()

    for title in RETIRED:
        assert title not in guide, "retired manual group came back: " + title


def test_the_theme_recipe_is_executable() -> None:
    """Renaming only `metadata.json` yields a theme the scope audit refuses.

    The guide has to send the reviewer through both halves: the metadata id and the selector
    that carries it in the CSS.

    重基线（Phase 12 GUI closeout）：配方本身未变，只是从 D1 移到了 D6（D1 现在是导入仓库内标本）。
    """
    recipe = _guide_steps(_guide_text()).get(("D", 6), "")
    missing = [token for token in THEME_RECIPE if token not in recipe]

    assert not missing, "the D6 theme recipe is not executable: " + ", ".join(missing)


@pytest.mark.parametrize("mark", [" ", "x", "X", " x ", "y"])
def test_a_checkbox_counts_as_one_item_whatever_its_state(mark: str) -> None:
    """A mark says whether an item passed, not whether the item exists."""
    record = "## A 启动与集成\n\n- [" + mark + "]  一\n- [" + mark + "]  二\n"

    assert _count_items(record) == [("A", 2)]


def test_the_mapping_holds_when_the_record_is_ticked() -> None:
    """12C ticks every box, so the mapping must be invariant under the checkbox state.

    Counting only unchecked boxes would turn "the acceptance run finished" into a structural
    failure. The guide contract stays green from 0/35 to 35/35; whether the run itself passed
    remains `release_freeze.qa_gate`'s decision.
    """
    original = CHECKLIST.read_text(encoding="utf-8")
    ticked = _flip_states(original)

    assert ticked != original, "the fixture has to actually change the checkbox states"
    assert _count_items(ticked) == _count_items(original), (
        "record item counts changed with the checkbox states: "
        + str(_count_items(ticked))
        + " vs "
        + str(_count_items(original))
    )
    assert _guide_counts(_guide_text()) == _count_items(ticked)
