"""Phase 5C 的网络端到端验收：**真实 bundled renderer** + 127.0.0.1 loopback 服务器。

它证明 roadmap 的三条硬验收：远程图片联网成功即成 standalone、断网/失败仍成功且保留原 URL、
PlantUML 抓图失败不导致整篇失败。

网络只发生在环回地址上（tests/loopback_http.py）：不访问公共互联网、不依赖 DNS、
不依赖拔网线或随机超时。细粒度传输语义（retry / Content-Type / 大小 / redirect）在
renderer/test/http_client.test.js；本套件证明它们在真实 dist 里确实生效。
"""

import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from loopback_http import LoopbackServer, running_loopback  # noqa: E402
from renderer_adapter import render  # noqa: E402

PNG_PREFIX = "data:image/png;base64,"
SVG_PREFIX = "data:image/svg+xml;base64,"
MISSING_REMOTE_WARNING = "远程资源无法内嵌，保留原引用："
PLANTUML_BLOCK = "@startuml\nA -> B\n@enduml\n"


@pytest.fixture()
def loopback() -> Iterator[LoopbackServer]:
    """每个用例一个全新的 127.0.0.1 临时端口服务器（含请求计数与并发峰值）。"""
    with running_loopback() as server:
        yield server


def img_sources(html: str) -> list[str]:
    return re.findall(r'\bsrc="([^"]*)"', html)


def img_source(html: str) -> str:
    sources = img_sources(html)
    assert sources, html
    return sources[0]


def items(envelope: dict, kind: str) -> list[dict]:
    return [item for item in envelope["resources"]["items"] if item["kind"] == kind]


def resource_order(envelope: dict) -> list[str]:
    return [
        item["kind"] + ":" + item["ref"]
        for item in envelope["resources"]["items"]
        if item["kind"] in ("image", "plantuml")
    ]


# --- 远程 Markdown 图片 -----------------------------------------------------


def test_a_remote_image_is_embedded_when_the_production_default_fetches(loopback):
    """不传 fetch 选项 → 走 renderer 生产默认（true），因此这条同时证明默认值是「联网抓取」。"""
    url = loopback.png("a.png")

    envelope = render("![图](" + url + ")\n", allow_network=True)

    assert img_source(envelope["html"]).startswith(PNG_PREFIX)
    (item,) = items(envelope, "image")
    assert item["source"] == "remote" and item["status"] == "inlined"
    assert item["ref"] == url and item["mime"] == "image/png"
    assert item["resolved"] == url
    assert envelope["warnings"] == []
    assert loopback.stats.count("/png/a.png") == 1


def test_a_redirect_records_the_final_url_but_keeps_the_author_reference(loopback):
    author_url = loopback.url("/redirect/a.png")

    envelope = render("![图](" + author_url + ")\n", allow_network=True)

    assert img_source(envelope["html"]).startswith(PNG_PREFIX)
    (item,) = items(envelope, "image")
    assert item["ref"] == author_url, "ref 必须保留作者原 URL"
    assert item["resolved"] == loopback.url("/png/a.png"), "resolved 记录最终 URL"
    assert loopback.stats.count("/redirect/a.png") == 1


def test_a_failed_remote_image_keeps_the_url_and_warns(loopback):
    url = loopback.url("/status/404")

    envelope = render("![图](" + url + ")\n", allow_network=True)

    assert img_source(envelope["html"]) == url, "失败时必须保留原引用"
    (item,) = items(envelope, "image")
    assert item["status"] == "failed" and item["ref"] == url
    assert "resolved" not in item
    assert len(envelope["warnings"]) == 1
    warning = envelope["warnings"][0]
    assert warning.startswith(MISSING_REMOTE_WARNING)
    assert url in warning and "HTTP 404" in warning
    assert loopback.stats.count("/status/404") == 1, "4xx 不 retry"


def test_a_server_error_is_retried_once_and_then_reported(loopback):
    url = loopback.url("/status/500")

    envelope = render("![图](" + url + ")\n", allow_network=True)

    assert img_source(envelope["html"]) == url
    assert items(envelope, "image")[0]["status"] == "failed"
    assert loopback.stats.count("/status/500") == 2, "5xx 恰好重试一次"
    assert "HTTP 500" in envelope["warnings"][0]


def test_retries_can_be_disabled_per_conversion(loopback):
    url = loopback.url("/status/503")

    envelope = render("![图](" + url + ")\n", {"resource_retries": 0}, allow_network=True)

    assert items(envelope, "image")[0]["status"] == "failed"
    assert loopback.stats.count("/status/503") == 1


def test_a_timeout_does_not_block_the_conversion(loopback):
    url = loopback.url("/slow/1500")

    envelope = render(
        "![图](" + url + ")\n",
        {"resource_timeout_ms": 300, "resource_retries": 0},
        allow_network=True,
    )

    assert img_source(envelope["html"]) == url
    assert items(envelope, "image")[0]["status"] == "failed"
    assert "请求超时" in envelope["warnings"][0]


def test_a_body_read_timeout_is_retried_and_reported_as_timeout(loopback):
    """头已返回、body 停住：必须按 timeout 分类并 retry（旧实现误报 network 且不重试）。"""
    url = loopback.url("/stall/1500")

    envelope = render("![图](" + url + ")\n", {"resource_timeout_ms": 300}, allow_network=True)

    assert img_source(envelope["html"]) == url, "失败必须保留原引用"
    (item,) = items(envelope, "image")
    assert item["status"] == "failed" and "resolved" not in item
    assert "请求超时" in envelope["warnings"][0], envelope["warnings"]
    assert loopback.stats.count("/stall/1500") == 2, "body 读取阶段的超时必须 retry 一次"


def test_a_body_read_failure_is_retried_and_reported_as_network(loopback):
    """声明长度与实际发送不符后断连：读取阶段属网络错误，必须 retry 一次。"""
    url = loopback.url("/truncate")

    envelope = render("![图](" + url + ")\n", {"resource_timeout_ms": 2000}, allow_network=True)

    assert img_source(envelope["html"]) == url
    assert items(envelope, "image")[0]["status"] == "failed"
    assert "网络错误" in envelope["warnings"][0], envelope["warnings"]
    assert loopback.stats.count("/truncate") == 2, "读取阶段的网络错误必须 retry 一次"


def test_an_oversized_resource_does_not_block_the_conversion(loopback):
    url = loopback.url("/oversized")

    envelope = render("![图](" + url + ")\n", {"resource_max_bytes": 4096}, allow_network=True)

    assert img_source(envelope["html"]) == url
    assert items(envelope, "image")[0]["status"] == "failed"
    assert "超过大小上限" in envelope["warnings"][0]


def test_a_chunked_body_over_the_limit_is_aborted(loopback):
    url = loopback.url("/chunky")

    envelope = render("![图](" + url + ")\n", {"resource_max_bytes": 4096}, allow_network=True)

    assert img_source(envelope["html"]) == url
    assert items(envelope, "image")[0]["status"] == "failed"
    assert "超过大小上限" in envelope["warnings"][0]


def test_a_non_image_response_is_never_embedded(loopback):
    url = loopback.url("/html/a.png")

    envelope = render("![图](" + url + ")\n", allow_network=True)

    assert img_source(envelope["html"]) == url
    assert items(envelope, "image")[0]["status"] == "failed"
    assert "响应不是图片" in envelope["warnings"][0]
    assert "data:" not in envelope["html"]


def test_a_missing_content_type_falls_back_to_the_extension(loopback):
    url = loopback.url("/plain/a.png")

    envelope = render("![图](" + url + ")\n", allow_network=True)

    assert img_source(envelope["html"]).startswith(PNG_PREFIX)
    assert items(envelope, "image")[0]["mime"] == "image/png"


def test_a_missing_content_type_without_extension_fails(loopback):
    url = loopback.url("/plain/no-extension")

    envelope = render("![图](" + url + ")\n", {"resource_retries": 0}, allow_network=True)

    assert img_source(envelope["html"]) == url
    assert "响应不是图片" in envelope["warnings"][0]


# --- 非法数值选项回落默认值（Phase 5C reliability closeout） ------------------


def test_a_negative_retries_option_falls_back_to_the_default(loopback):
    """-1 曾让重试循环一次都不执行（零请求 + network 失败）；必须回落默认 1（共 2 次尝试）。"""
    url = loopback.url("/status/503")

    envelope = render("![图](" + url + ")\n", {"resource_retries": -1}, allow_network=True)

    assert loopback.stats.count("/status/503") == 2, "负数必须回落默认值，而不是一次请求都不发"
    assert items(envelope, "image")[0]["status"] == "failed"
    assert "HTTP 503" in envelope["warnings"][0], envelope["warnings"]


def test_a_non_positive_timeout_falls_back_to_the_default(loopback):
    """0 ms 超时会立刻 abort；回落 8000 ms 后这个 300 ms 的响应必须成功内嵌。"""
    url = loopback.url("/slow/300")

    envelope = render("![图](" + url + ")\n", {"resource_timeout_ms": 0}, allow_network=True)

    assert img_source(envelope["html"]).startswith(PNG_PREFIX)
    assert items(envelope, "image")[0]["status"] == "inlined"
    assert envelope["warnings"] == []
    assert loopback.stats.count("/slow/300") == 1


def test_a_non_positive_max_bytes_falls_back_to_the_default(loopback):
    """0 B 上限会把任何资源判为超限；回落 16 MiB 后必须内嵌成功。"""
    url = loopback.png("small.png")

    envelope = render("![图](" + url + ")\n", {"resource_max_bytes": 0}, allow_network=True)

    assert img_source(envelope["html"]).startswith(PNG_PREFIX)
    assert items(envelope, "image")[0]["status"] == "inlined"
    assert envelope["warnings"] == []


# --- 协议相对 URL -----------------------------------------------------------


def test_a_protocol_relative_url_keeps_the_author_form_on_failure(loopback):
    """抓取目标是 https（loopback 只有 http，因此必然失败），但 fallback 必须是作者原文。"""
    author_url = "//127.0.0.1:" + str(loopback.port) + "/png/a.png"

    envelope = render("![图](" + author_url + ")\n", {"resource_retries": 0}, allow_network=True)

    assert img_source(envelope["html"]) == author_url, "不得把 fallback 改写成 https:"
    (item,) = items(envelope, "image")
    assert item["ref"] == author_url and item["status"] == "failed"
    assert author_url in envelope["warnings"][0]
    assert loopback.stats.count("/png/a.png") == 0, "协议相对必须走 https，不能落到本地 http 端口"


# --- 去重、顺序与并发 -------------------------------------------------------


def test_duplicate_remote_urls_are_fetched_once_and_all_occurrences_are_inlined(loopback):
    url = loopback.png("dup.png")
    markdown = "![a](" + url + ")\n\n![b](" + url + ")\n\n![c](" + url + ")\n"

    envelope = render(markdown, allow_network=True)

    assert loopback.stats.count("/png/dup.png") == 1, "同一 URL 只能真正请求一次"
    sources = img_sources(envelope["html"])
    assert len(sources) == 3 and all(src.startswith(PNG_PREFIX) for src in sources)
    assert [item["status"] for item in items(envelope, "image")] == ["inlined"] * 3
    assert envelope["warnings"] == []


def test_a_duplicate_failing_url_warns_once(loopback):
    url = loopback.url("/status/404")
    markdown = "![a](" + url + ")\n\n![b](" + url + ")\n\n![c](" + url + ")\n"

    envelope = render(markdown, allow_network=True)

    assert loopback.stats.count("/status/404") == 1
    assert [item["status"] for item in items(envelope, "image")] == ["failed"] * 3
    assert len(envelope["warnings"]) == 1, "同一 URL 的同一失败只报一次"


def test_manifest_and_warning_order_follow_the_document(loopback):
    """第 1 个资源最慢：完成顺序与文档顺序不同，但 manifest / warnings 必须仍是文档顺序。"""
    slow = loopback.url("/slow/300")
    missing = loopback.url("/status/404")
    ok = loopback.png("b.png")
    markdown = "![slow](" + slow + ")\n\n![missing](" + missing + ")\n\n![ok](" + ok + ")\n"

    envelope = render(markdown, allow_network=True)

    assert resource_order(envelope) == ["image:" + slow, "image:" + missing, "image:" + ok]
    assert [item["status"] for item in items(envelope, "image")] == [
        "inlined",
        "failed",
        "inlined",
    ]
    assert len(envelope["warnings"]) == 1 and missing in envelope["warnings"][0]


def test_concurrent_fetches_respect_the_limit(loopback):
    # 8 个**不同**的 URL：相同 URL 会被 cache 合并成一次请求，那样看不出并发。
    urls = [loopback.url("/slow/150?i=" + str(index)) for index in range(8)]
    markdown = "".join("![" + str(index) + "](" + url + ")\n\n" for index, url in enumerate(urls))

    envelope = render(markdown, allow_network=True)

    assert len(items(envelope, "image")) == 8
    assert all(item["status"] == "inlined" for item in items(envelope, "image"))
    assert loopback.stats.count("/slow/150") == 8, "8 个不同 URL 应各请求一次"
    assert loopback.stats.max_in_flight <= 4, (
        "并发上限必须生效：" + str(loopback.stats.max_in_flight)
    )
    assert loopback.stats.max_in_flight >= 2, (
        "应当真的并发执行：" + str(loopback.stats.max_in_flight)
    )


def test_fetch_remote_resources_false_never_touches_the_network(loopback):
    url = loopback.png("off.png")

    envelope = render("![图](" + url + ")\n", {"fetch_remote_resources": False})

    assert img_source(envelope["html"]) == url
    (item,) = items(envelope, "image")
    assert item["status"] == "kept" and item["ref"] == url
    assert envelope["warnings"] == [], "用户明确关闭抓取不是失败"
    assert loopback.stats.count("/png/off.png") == 0


# --- raw HTML 边界 ----------------------------------------------------------


def test_a_raw_html_remote_image_is_never_fetched(loopback):
    url = loopback.png("raw.png")
    markdown = '<img src="' + url + '" alt="raw">\n'

    envelope = render(markdown, allow_network=True)

    assert '<img src="' + url + '"' in envelope["html"], "raw HTML 原样保留"
    assert envelope["resources"]["items"] == []
    assert envelope["warnings"] == []
    assert loopback.stats.count("/png/raw.png") == 0, "raw HTML 不得触发抓取"


# --- PlantUML ---------------------------------------------------------------


def test_plantuml_is_embedded_when_the_server_answers(loopback):
    envelope = render(
        PLANTUML_BLOCK,
        {"plantuml_server": loopback.url("/svg")},
        allow_network=True,
    )

    assert envelope["features"]["plantuml"] is True
    assert img_source(envelope["html"]).startswith(SVG_PREFIX)
    (item,) = items(envelope, "plantuml")
    assert item["source"] == "remote" and item["status"] == "inlined"
    assert item["mime"] == "image/svg+xml"
    assert item["ref"].startswith(loopback.url("/svg") + "/svg/")
    assert envelope["warnings"] == []


def test_a_plantuml_failure_keeps_the_server_url_and_the_feature(loopback):
    server = loopback.url("/missing")

    envelope = render(PLANTUML_BLOCK, {"plantuml_server": server}, allow_network=True)

    assert envelope["features"]["plantuml"] is True, "资源失败不得改变语义 feature"
    src = img_source(envelope["html"])
    assert src.startswith(server + "/svg/"), "失败必须保留原 PlantUML URL"
    assert "data:" not in envelope["html"]
    (item,) = items(envelope, "plantuml")
    assert item["status"] == "failed"
    assert len(envelope["warnings"]) == 1
    assert "HTTP 404" in envelope["warnings"][0]


def test_a_plantuml_failure_does_not_block_the_rest_of_the_document(loopback):
    markdown = "# 标题\n\n" + PLANTUML_BLOCK + "\n正文仍然存在。\n"

    envelope = render(markdown, {"plantuml_server": loopback.url("/missing")}, allow_network=True)

    assert "<h1" in envelope["html"] and "正文仍然存在。" in envelope["html"]
    assert img_source(envelope["html"]).startswith(loopback.url("/missing"))
