from pathlib import Path

from core.conversion_plan import build_conversion_plan


def test_multiple_selected_files_build_one_explicit_plan(tmp_path: Path):
    source = tmp_path / "CPA 笔记"
    output = tmp_path / "output"
    source.mkdir()
    chapter_19 = source / "第19章 所得税.md"
    chapter_24 = source / "第24章 差错更正.md"
    chapter_19.write_text("# 所得税", encoding="utf-8")
    chapter_24.write_text("# 差错更正", encoding="utf-8")

    plan = build_conversion_plan(
        [str(chapter_19), str(chapter_24)],
        str(output),
        preserve_structure=False,
    )

    assert plan["errors"] == []
    assert plan["counts"] == {"selected": 2, "directory": 0, "dependency": 0, "total": 2}
    assert {Path(item["output_path"]).name for item in plan["items"]} == {
        "第19章 所得税.html",
        "第24章 差错更正.html",
    }


def test_directory_plan_preserves_relative_structure(tmp_path: Path):
    source = tmp_path / "笔记库"
    nested = source / "专题"
    nested.mkdir(parents=True)
    document = nested / "收入.md"
    document.write_text("# 收入", encoding="utf-8")

    plan = build_conversion_plan([str(source)], str(tmp_path / "发布"), preserve_structure=True)

    assert plan["errors"] == []
    assert Path(plan["output_dir"]).name == "笔记库-HTML"
    assert plan["items"][0]["output_relative"].replace("\\", "/") == "专题/收入.html"
    assert plan["items"][0]["origin"] == "directory"


def test_flat_output_collision_is_blocked_before_writing(tmp_path: Path):
    source = tmp_path / "笔记库"
    first = source / "金融" / "概述.md"
    second = source / "收入" / "概述.md"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("# 金融", encoding="utf-8")
    second.write_text("# 收入", encoding="utf-8")

    plan = build_conversion_plan([str(source)], str(tmp_path / "发布"), preserve_structure=False)

    assert len(plan["items"]) == 2
    assert any("输出文件冲突" in error for error in plan["errors"])


def test_duplicate_file_and_directory_input_is_deduplicated(tmp_path: Path):
    source = tmp_path / "笔记库"
    source.mkdir()
    document = source / "第1章.md"
    document.write_text("# 第一章", encoding="utf-8")

    plan = build_conversion_plan([str(source), str(document)], str(tmp_path / "发布"))

    assert len(plan["items"]) == 1
    assert plan["items"][0]["origin"] == "selected"

