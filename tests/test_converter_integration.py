import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import load_config  # noqa: E402
from core.conversion_plan import build_conversion_plan  # noqa: E402
from core.converter import process_batch  # noqa: E402


def test_batch_conversion_writes_footnotes_and_cross_document_html_links(tmp_path: Path):
    source = tmp_path / "CPA 笔记"
    output = tmp_path / "HTML"
    source.mkdir()
    chapter_20 = source / "第20章.md"
    chapter_24 = source / "第24章.md"
    chapter_20.write_text("# 第二十章\n\n## 第二节", encoding="utf-8")
    chapter_24.write_text(
        "# 第二十四章\n\n计量方法[^chapter]\n\n"
        "[^chapter]: 参见[第20章](./第20章.md#第二节)。",
        encoding="utf-8",
    )

    plan = build_conversion_plan([str(chapter_20), str(chapter_24)], str(output))
    config = load_config(
        runtime_overrides={"template": "modern", "build_index": False, "auto_open": False}
    )
    results = process_batch(
        [str(chapter_20), str(chapter_24)],
        str(output),
        config,
        plan=plan,
    )

    assert len(results) == 2
    html = (output / "第24章.html").read_text(encoding="utf-8")
    assert 'class="footnote-ref"' in html
    assert 'class="footnotes"' in html
    assert "%E7%AC%AC20%E7%AB%A0.html#%E7%AC%AC%E4%BA%8C%E8%8A%82" in html
    assert "[^chapter]" not in html


def test_only_the_document_with_a_formula_carries_the_katex_fonts(tmp_path: Path):
    """The renderer decides, and nothing downstream puts the fonts back."""
    source = tmp_path / "笔记"
    output = tmp_path / "HTML"
    source.mkdir()
    plain = source / "无公式.md"
    formula = source / "有公式.md"
    plain.write_text("# 无公式\n\n这里只有普通文本。", encoding="utf-8")
    formula.write_text("# 有公式\n\n圆的面积 $A = \\pi r^2$。", encoding="utf-8")

    plan = build_conversion_plan([str(plain), str(formula)], str(output))
    config = load_config(
        runtime_overrides={"template": "modern", "build_index": False, "auto_open": False}
    )
    results = process_batch([str(plain), str(formula)], str(output), config, plan=plan)

    assert len(results) == 2
    plain_html = (output / "无公式.html").read_text(encoding="utf-8")
    formula_html = (output / "有公式.html").read_text(encoding="utf-8")

    assert "KaTeX_AMS" not in plain_html
    assert "data:font/woff2" not in plain_html
    assert "KaTeX_AMS" in formula_html
    assert len(plain_html) * 5 < len(formula_html), (
        "a page without a formula must stay in template sized territory"
    )
