"""Phase 5D：standalone closure checker 的行为契约（不依赖 node / 网络）。

这里用合成 HTML 固定 checker 的判定语义：哪些引用算 subresource、四种 verdict 各自的
证据要求、以及「声明不能遮蔽真实 regression」的反遮蔽规则。真实 adapter + assembler
的端到端矩阵在 `test_standalone_matrix.py`。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.standalone_closure import collect_subresources, main, scan  # noqa: E402

EXTERNAL_IMAGE = "https://cdn.example.invalid/a.png"
EXTERNAL_FONT = "https://cdn.example.invalid/font.woff2"


def _page(body: str) -> str:
    return "<!doctype html><html><head></head><body>" + body + "</body></html>"


def _envelope(html: str = "", items=None, warnings=None) -> dict:
    return {
        "protocol_version": 2,
        "ok": True,
        "html": html,
        "headings": [],
        "warnings": list(warnings or []),
        "resources": {"items": list(items or []), "styles": [], "scripts": []},
    }


def _image_item(status: str, ref: str = EXTERNAL_IMAGE, source: str = "remote") -> dict:
    return {"kind": "image", "source": source, "ref": ref, "status": status}


def _refs(found: list[dict]) -> list[str]:
    return [entry["ref"] for entry in found]


# --- subresource 识别 -------------------------------------------------------


def test_collect_subresources_covers_img_script_link_and_controlled_css():
    html = _page(
        '<img src="' + EXTERNAL_IMAGE + '">'
        '<script src="https://cdn.example.invalid/x.js"></script>'
        '<link rel="stylesheet" href="https://cdn.example.invalid/x.css">'
        "<style>@font-face{src:url(" + EXTERNAL_FONT + ")}</style>"
    )

    found = collect_subresources(html)

    assert EXTERNAL_IMAGE in _refs(found)
    assert "https://cdn.example.invalid/x.js" in _refs(found)
    assert "https://cdn.example.invalid/x.css" in _refs(found)
    assert EXTERNAL_FONT in _refs(found), "受控 CSS 的 url() 必须被发现"
    assert [entry["element"] for entry in found if entry["ref"] == EXTERNAL_FONT] == ["style"]


DATA_PNG = "data:image/png;base64,AAAA"


def test_srcset_candidates_are_checked_individually():
    html = _page(
        '<img src="' + DATA_PNG + '" srcset="' + DATA_PNG + ' 1x, ' + EXTERNAL_IMAGE + ' 2x">'
    )

    report = scan(html)

    assert _refs(collect_subresources(html)) == [DATA_PNG, DATA_PNG, EXTERNAL_IMAGE]
    assert report["verdict"] == "failure", report


def test_a_data_uri_srcset_produces_no_pseudo_reference():
    """data URI 自带逗号：按逗号 split 会凭空造出外部引用（5D 首轮就是这个 bug）。"""
    html = _page('<img srcset="' + DATA_PNG + ' 1x">')

    found = collect_subresources(html)
    report = scan(html)

    assert _refs(found) == [DATA_PNG]
    assert report["verdict"] == "standalone"
    assert report["unexplained_external_resources"] == []


def test_srcset_descriptors_and_line_breaks_stay_out_of_the_references():
    html = _page('<img srcset="a.png 1x, b.png 2x,\n             c.png 480w">')

    assert _refs(collect_subresources(html)) == ["a.png", "b.png", "c.png"]


def test_navigation_links_and_plain_text_are_not_subresources():
    html = _page(
        '<a href="https://example.invalid/page">外链</a>'
        '<a href="mailto:someone@example.invalid">邮件</a>'
        "<p>正文里出现 http://example.invalid 也只是文字。</p>"
    )

    report = scan(html)

    assert collect_subresources(html) == []
    assert report["verdict"] == "standalone"
    assert report["payload"]["total_bytes"] > 0


def test_inline_style_attribute_urls_are_scanned():
    """K13 只说不改 raw HTML，不等于浏览器不会加载它：style 属性的 url() 必须被扫描。"""
    html = _page('<div style="background-image:url(' + EXTERNAL_IMAGE + ')">x</div>')

    found = collect_subresources(html)

    assert _refs(found) == [EXTERNAL_IMAGE]
    assert [entry["origin"] for entry in found] == ["style-attr"]
    assert scan(html)["verdict"] == "failure"


def test_a_declared_style_attribute_url_is_an_author_reference():
    html = _page('<div style="background-image:url(' + EXTERNAL_IMAGE + ')">x</div>')

    report = scan(html, envelope=_envelope(html=html), author_owned_refs=[EXTERNAL_IMAGE])

    assert report["verdict"] == "author_references"
    assert [entry["ref"] for entry in report["author_references"]] == [EXTERNAL_IMAGE]
    assert report["problems"] == []


def test_data_uri_and_fragment_references_are_inline():
    html = _page(
        '<img src="data:image/png;base64,AAAA">'
        '<script src="#nothing"></script>'
        "<style>body{background:url('data:image/gif;base64,AAAA')}</style>"
    )

    assert scan(html)["verdict"] == "standalone"


# --- evidence 与 verdict ----------------------------------------------------


def test_an_external_subresource_without_any_evidence_is_a_failure():
    html = _page('<img src="' + EXTERNAL_IMAGE + '">')

    report = scan(html)

    assert report["verdict"] == "failure"
    assert report["standalone"] is False
    assert [entry["ref"] for entry in report["unexplained_external_resources"]] == [EXTERNAL_IMAGE]
    assert report["problems"], "failure 必须给出原因"
    assert report["degraded_resources"] == []
    assert report["author_references"] == []


def test_a_declared_author_reference_is_reported_separately_from_a_fallback():
    html = _page('<img src="' + EXTERNAL_IMAGE + '">')
    envelope = _envelope(html='<img src="' + EXTERNAL_IMAGE + '">')

    report = scan(html, envelope=envelope, author_owned_refs=[EXTERNAL_IMAGE])

    assert report["verdict"] == "author_references"
    assert [entry["ref"] for entry in report["author_references"]] == [EXTERNAL_IMAGE]
    assert report["degraded_resources"] == []
    assert report["unexplained_external_resources"] == []
    assert report["problems"] == []


def test_a_declaration_the_renderer_never_produced_is_a_failure():
    """声明必须被 renderer fragment 佐证，否则不能拿它遮蔽 regression。"""
    html = _page('<img src="' + EXTERNAL_IMAGE + '">')
    envelope = _envelope(html="<p>no image here</p>")

    report = scan(html, envelope=envelope, author_owned_refs=[EXTERNAL_IMAGE])

    assert report["verdict"] == "failure"
    assert report["author_references"] == []
    assert report["unexplained_external_resources"]


def test_a_declaration_missing_from_the_document_is_a_failure():
    html = _page("<p>没有图片</p>")
    envelope = _envelope(html='<img src="' + EXTERNAL_IMAGE + '">')

    report = scan(html, envelope=envelope, author_owned_refs=[EXTERNAL_IMAGE])

    assert report["verdict"] == "failure"
    assert any(EXTERNAL_IMAGE in problem for problem in report["problems"])


def test_a_markdown_image_the_layer_never_claimed_cannot_be_declared_away():
    """反遮蔽：Markdown 图片漏收集时，未声明的引用必须判 failure。"""
    html = _page('<img src="' + EXTERNAL_IMAGE + '">')
    envelope = _envelope(html='<img src="' + EXTERNAL_IMAGE + '">', items=[])

    report = scan(html, envelope=envelope)

    assert report["verdict"] == "failure"
    assert report["author_references"] == []
    assert [entry["ref"] for entry in report["unexplained_external_resources"]] == [EXTERNAL_IMAGE]

def test_a_failed_manifest_item_with_a_warning_is_degraded():
    html = _page('<img src="' + EXTERNAL_IMAGE + '">')
    envelope = _envelope(
        html='<img src="' + EXTERNAL_IMAGE + '">',
        items=[_image_item("failed")],
        warnings=["远程资源无法内嵌，保留原引用：" + EXTERNAL_IMAGE + "（HTTP 404）"],
    )

    report = scan(html, envelope=envelope)

    assert report["verdict"] == "degraded"
    assert report["unexplained_external_resources"] == []
    item = report["degraded_resources"][0]
    assert item["ref"] == EXTERNAL_IMAGE
    assert item["occurrences"] == 1
    assert item["evidence"]["failed"] == 1
    assert item["evidence"]["warning"]


def test_a_failed_manifest_item_without_a_warning_is_a_failure():
    html = _page('<img src="' + EXTERNAL_IMAGE + '">')
    envelope = _envelope(
        html='<img src="' + EXTERNAL_IMAGE + '">', items=[_image_item("failed")]
    )

    report = scan(html, envelope=envelope)

    assert report["verdict"] == "failure"
    assert any("warning" in problem for problem in report["problems"])


def test_a_kept_manifest_item_does_not_require_a_warning():
    """5C 的 kept（关闭联网、本地无基准）本来就不产生 warning。"""
    html = _page('<img src="' + EXTERNAL_IMAGE + '">')
    envelope = _envelope(
        html='<img src="' + EXTERNAL_IMAGE + '">', items=[_image_item("kept")]
    )

    report = scan(html, envelope=envelope)

    assert report["verdict"] == "degraded"
    assert report["degraded_resources"][0]["evidence"]["kept"] == 1


def test_an_item_claimed_inlined_but_still_external_is_a_failure():
    """反证：manifest 说内嵌了，文档里却还是外链 —— 这是真 regression。"""
    html = _page('<img src="' + EXTERNAL_IMAGE + '">')
    envelope = _envelope(
        html='<img src="' + EXTERNAL_IMAGE + '">', items=[_image_item("inlined")]
    )

    report = scan(html, envelope=envelope)

    assert report["verdict"] == "failure"
    assert report["degraded_resources"] == []


def test_degraded_outranks_author_references_and_keeps_both_buckets():
    author_ref = "https://raw.example.invalid/author.png"
    html = _page('<img src="' + EXTERNAL_IMAGE + '"><img src="' + author_ref + '">')
    envelope = _envelope(
        html='<img src="' + EXTERNAL_IMAGE + '"><img src="' + author_ref + '">',
        items=[_image_item("failed")],
        warnings=["远程资源无法内嵌，保留原引用：" + EXTERNAL_IMAGE + "（超时）"],
    )

    report = scan(html, envelope=envelope, author_owned_refs=[author_ref])

    assert report["verdict"] == "degraded"
    assert [entry["ref"] for entry in report["degraded_resources"]] == [EXTERNAL_IMAGE]
    assert [entry["ref"] for entry in report["author_references"]] == [author_ref]
    assert report["severity_order"][0] == "failure"
    assert report["severity_order"][-1] == "standalone"


def test_failure_outranks_degraded_and_keeps_every_bucket():
    missing = "https://cdn.example.invalid/unexplained.png"
    html = _page('<img src="' + EXTERNAL_IMAGE + '"><img src="' + missing + '">')
    envelope = _envelope(
        html='<img src="' + EXTERNAL_IMAGE + '"><img src="' + missing + '">',
        items=[_image_item("failed")],
        warnings=["远程资源无法内嵌，保留原引用：" + EXTERNAL_IMAGE + "（超时）"],
    )

    report = scan(html, envelope=envelope)

    assert report["verdict"] == "failure"
    assert report["degraded_resources"], "degraded 桶不得被 failure 吞掉"
    assert report["unexplained_external_resources"]

# --- occurrence 多重性 -------------------------------------------------------


def _same_url_html(count: int) -> str:
    single = '<img src="' + EXTERNAL_IMAGE + '">'
    return _page(single * count)


def test_an_inlined_manifest_still_allows_the_author_occurrence():
    """同 URL：Markdown 图片已内嵌，作者 raw HTML 的那一份仍是 author_references。"""
    html = _same_url_html(1)
    envelope = _envelope(html=html, items=[_image_item("inlined")])

    report = scan(html, envelope=envelope, author_owned_refs=[EXTERNAL_IMAGE])

    assert report["verdict"] == "author_references"
    assert [entry["ref"] for entry in report["author_references"]] == [EXTERNAL_IMAGE]
    assert report["unexplained_external_resources"] == []
    assert report["occurrences"] == [
        {
            "ref": EXTERNAL_IMAGE,
            "final": 1,
            "degraded": 0,
            "author": 1,
            "unexplained": 0,
            "manifest": {"inlined": 1, "failed": 0, "kept": 0},
            "declared_author": 1,
            "warning": None,
        }
    ]


def test_an_author_declaration_cannot_cover_extra_occurrences():
    """同 URL：inlined manifest + 1 处声明，但最终 2 处外链 → failure。"""
    html = _same_url_html(2)
    envelope = _envelope(html=html, items=[_image_item("inlined")])

    report = scan(html, envelope=envelope, author_owned_refs=[EXTERNAL_IMAGE])

    assert report["verdict"] == "failure"
    assert report["author_references"][0]["occurrences"] == 1
    assert report["unexplained_external_resources"][0]["occurrences"] == 1
    assert [entry["status"] for entry in report["subresources"]] == ["author", "unexplained"]


def test_a_failed_occurrence_and_an_author_occurrence_share_one_url():
    """同 URL：Markdown 抓取失败 + 作者 raw HTML → degraded 1 处 + author 1 处。"""
    html = _same_url_html(2)
    envelope = _envelope(
        html=html,
        items=[_image_item("failed")],
        warnings=["远程资源无法内嵌，保留原引用：" + EXTERNAL_IMAGE + "（超时）"],
    )

    report = scan(html, envelope=envelope, author_owned_refs=[EXTERNAL_IMAGE])

    assert report["verdict"] == "degraded"
    assert report["degraded_resources"][0]["occurrences"] == 1
    assert report["author_references"][0]["occurrences"] == 1
    assert report["unexplained_external_resources"] == []
    assert [entry["status"] for entry in report["subresources"]] == ["degraded", "author"]


def test_one_warning_covers_every_failed_occurrence_of_a_url():
    """5C 同一 URL 的同一失败只报一次 warning，因此 warning 按 ref 共享。"""
    html = _same_url_html(3)
    envelope = _envelope(
        html=html,
        items=[_image_item("failed")] * 3,
        warnings=["远程资源无法内嵌，保留原引用：" + EXTERNAL_IMAGE + "（HTTP 404）"],
    )

    report = scan(html, envelope=envelope)

    assert report["verdict"] == "degraded"
    assert report["degraded_resources"][0]["occurrences"] == 3
    assert report["problems"] == []


def test_a_declaration_with_an_explicit_count_is_honoured():
    html = _same_url_html(2)

    report = scan(
        html,
        envelope=_envelope(html=html),
        author_owned_refs=[{"ref": EXTERNAL_IMAGE, "count": 2}],
    )

    assert report["verdict"] == "author_references"
    assert report["author_references"][0]["occurrences"] == 2


def test_a_declaration_beyond_the_renderer_fragment_is_a_failure():
    """声明数量不得超过 renderer fragment 里真实产生的次数。"""
    html = _same_url_html(2)
    envelope = _envelope(html=_same_url_html(1))

    report = scan(
        html,
        envelope=envelope,
        author_owned_refs=[{"ref": EXTERNAL_IMAGE, "count": 2}],
    )

    assert report["verdict"] == "failure"
    assert any("只有 1 处" in problem for problem in report["problems"])
    assert report["author_references"][0]["occurrences"] == 1
    assert report["unexplained_external_resources"][0]["occurrences"] == 1


# --- link rel 与 @import -----------------------------------------------------


def test_a_canonical_link_is_not_a_subresource():
    html = _page('<link rel="canonical" href="https://example.invalid/page">')

    assert collect_subresources(html) == []
    assert scan(html)["verdict"] == "standalone"


def test_stylesheet_icon_preload_and_rel_less_links_are_subresources():
    href = "https://cdn.example.invalid/x.css"
    for rel in ("stylesheet", "icon", "preload", None):
        markup = (
            "<link href=\"" + href + "\">"
            if rel is None
            else '<link rel="' + rel + '" href="' + href + '">'
        )

        assert [entry["ref"] for entry in collect_subresources(_page(markup))] == [href], rel
        assert scan(_page(markup))["verdict"] == "failure", rel


def test_an_alternate_stylesheet_is_still_a_subresource():
    """`alternate stylesheet` 仍是 external resource link，只是不是默认样式表。"""
    href = "https://cdn.example.invalid/high-contrast.css"
    html = _page('<link rel="alternate stylesheet" href="' + href + '" title="High contrast">')

    assert [entry["ref"] for entry in collect_subresources(html)] == [href]
    assert scan(html)["verdict"] == "failure"


def test_a_fetching_rel_token_wins_over_a_non_fetching_one():
    """混合 rel：出现 fetching token 就必须算 subresource（`author` 不能把它掩掉）。"""
    href = "https://cdn.example.invalid/x.css"
    for rel in ("author stylesheet", "dns-prefetch preload", "alternate icon"):
        html = _page('<link rel="' + rel + '" href="' + href + '">')

        assert [entry["ref"] for entry in collect_subresources(html)] == [href], rel
        assert scan(html)["verdict"] == "failure", rel


def test_metadata_only_rels_are_ignored():
    href = "https://example.invalid/whatever"
    for rel in ("canonical", "alternate", "dns-prefetch preconnect", "prev next", "license help"):
        html = _page('<link rel="' + rel + '" href="' + href + '">')

        assert collect_subresources(html) == [], rel
        assert scan(html)["verdict"] == "standalone", rel


def test_an_unknown_rel_is_a_subresource():
    href = "https://cdn.example.invalid/x.css"
    for rel in ("something-new", "canonical something-new"):
        html = _page('<link rel="' + rel + '" href="' + href + '">')

        assert [entry["ref"] for entry in collect_subresources(html)] == [href], rel
        assert scan(html)["verdict"] == "failure", rel


def test_a_string_form_import_is_a_subresource():
    html = _page('<style>@import "https://cdn.example.invalid/theme.css";</style>')

    found = collect_subresources(html)

    assert [entry["attribute"] for entry in found] == ["@import"]
    assert scan(html)["verdict"] == "failure"


def test_a_url_form_import_is_still_a_subresource():
    """`@import url(...)` 仍必须让 gate 失败；Phase 7 follow-up 后按 at-rule 记一次账。

    共享扫描器把整条 at-rule 当作一个引用（不再额外地把它里面的 url() 再报一次），
    所以形式是 `@import` 而不是 `url()`：结论不变，仍是 failure。
    """
    html = _page("<style>@import url(https://cdn.example.invalid/theme.css);</style>")

    found = collect_subresources(html)

    assert [entry["attribute"] for entry in found] == ["@import"]
    assert scan(html)["verdict"] == "failure"


# --- 体积报告 ---------------------------------------------------------------


def test_payload_report_uses_the_injection_ledger():
    injections = [
        {"position": "head", "label": "viewer-css", "id": None, "bytes": 100},
        {"position": "head", "label": "theme", "id": None, "bytes": 200},
        {"position": "head", "label": "style:katex", "id": "katex", "bytes": 300},
        {"position": "body", "label": "viewer-js", "id": None, "bytes": 400},
        {"position": "body", "label": "script:mermaid", "id": "mermaid", "bytes": 500},
    ]

    report = scan(_page("<p>" + "x" * 2000 + "</p>"), injections=injections)

    payload = report["payload"]
    assert payload["injected_bytes"] == 1500
    assert payload["resource_payload_bytes"] == 800, "只有资源载荷计入"
    assert payload["document_bytes"] == payload["total_bytes"] - 1500
    assert payload["document_bytes"] > 0


# --- CLI --------------------------------------------------------------------


def test_cli_exits_zero_for_a_standalone_document(tmp_path, capsys):
    page = tmp_path / "ok.html"
    page.write_text(_page('<img src="data:image/png;base64,AAAA">'), encoding="utf-8")

    code = main([str(page)])

    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["verdict"] == "standalone"


def test_cli_is_strict_without_an_envelope(tmp_path, capsys):
    page = tmp_path / "external.html"
    page.write_text(_page('<img src="' + EXTERNAL_IMAGE + '">'), encoding="utf-8")

    code = main([str(page)])

    report = json.loads(capsys.readouterr().out)
    assert code == 1
    assert report["verdict"] == "failure"


def test_cli_accepts_envelope_and_author_declarations(tmp_path, capsys):
    page = tmp_path / "author.html"
    page.write_text(_page('<img src="' + EXTERNAL_IMAGE + '">'), encoding="utf-8")
    envelope = tmp_path / "envelope.json"
    envelope.write_text(
        json.dumps(_envelope(html='<img src="' + EXTERNAL_IMAGE + '">')), encoding="utf-8"
    )
    refs = tmp_path / "author-refs.json"
    refs.write_text(json.dumps([EXTERNAL_IMAGE]), encoding="utf-8")

    code = main([str(page), "--envelope", str(envelope), "--author-refs", str(refs)])

    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["verdict"] == "author_references"
