from pathlib import Path

from core.config import load_config
from core.conversion_plan import build_conversion_plan
from core.converter import process_batch


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
        cli_overrides={"template": "modern", "build_index": False, "auto_open": False}
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
