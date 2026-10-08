"""G2 gates: real process reuse, one-shot equivalence, isolation, and bounded cleanup."""

import ast
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from renderer_adapter import require_node, run_adapter  # noqa: E402

from core import renderer_node, renderer_session, renderer_v2  # noqa: E402
from core.renderer_session import RendererSession  # noqa: E402
from tools.generate_demo import generate_demo  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_session(monkeypatch):
    renderer_v2.close_renderer_session()
    monkeypatch.setattr(renderer_node, "_RESOLVED_NODE", None)
    monkeypatch.setattr(renderer_node, "_RESOLVED_NODE_VERSION", None)
    yield
    renderer_v2.close_renderer_session()


@pytest.fixture
def spawned_renderers(monkeypatch):
    original = subprocess.Popen
    children = []

    def observe(args, **kwargs):
        child = original(args, **kwargs)
        if any(str(arg).endswith("renderer.cjs") for arg in args):
            children.append((list(args), child))
        return child

    monkeypatch.setattr(renderer_session.subprocess, "Popen", observe)
    return children


def test_six_production_conversions_share_one_real_node_and_preserve_demo_bytes(
    tmp_path: Path, spawned_renderers,
):
    require_node()
    expected = (ROOT / "samples" / "demo.html").read_bytes()
    pids = []
    for index in range(6):
        output = generate_demo(output=tmp_path / f"demo-{index}.html")
        assert output.read_bytes() == expected
        session = renderer_v2._DEFAULT_BRIDGE._session
        assert session is not None
        pids.append(session.pid)
    assert len(spawned_renderers) == 1, "包含首次 smoke，整个生产转换序列只能启动一次 renderer"
    args, child = spawned_renderers[0]
    assert args[-1] == "--server"
    assert pids == [child.pid] * 6
    assert child.poll() is None
    renderer_v2.close_renderer_session()
    assert child.poll() == 0, "正常 close 必须通过 EOF 退出并回收进程"


def test_concurrent_production_callers_share_one_child_without_crossed_responses(spawned_renderers):
    require_node()
    documents = [f"# Document {index}\n\nLine {index}." for index in range(12)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        envelopes = list(pool.map(renderer_node.render_markdown_node, documents))
    for index, envelope in enumerate(envelopes):
        assert f"Document {index}</h1>" in envelope["html"]
        assert f"Line {index}." in envelope["html"]
    assert len(spawned_renderers) == 1


def test_server_matches_one_shot_across_options_contexts_and_large_resources(tmp_path: Path):
    node = require_node()
    session = RendererSession(node, renderer_v2.require_artifact())
    context = {"source_path": str(tmp_path / "中文 空格.md")}
    image = tmp_path / "image.svg"
    image.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>one</text></svg>')
    requests = [
        ("# 重复\n\n# 重复\n\nfootnote[^1].\n\n[^1]: note", {}),
        ("# 公式\n\n$a^2$", {"math": True}),
        ("# 公式\n\n$a^2$", {"math": False}),
        ("```mermaid\ngraph TD; A-->B;\n```", {}),
        ("plain document", {}),
        ("# 重复\n\n# 重复\n\nfootnote[^1].\n\n[^1]: note", {}),
        ("![图](image.svg)\n\n[next](next.md)", {}),
        ("$b^2$\n\nmissing: ![图](missing.png)", {"math": True}),
    ]
    try:
        generation = session.start()
        pid = session.pid
        for markdown, options in requests:
            payload = {
                "markdown": markdown,
                "options": {"fetch_remote_resources": False, **options},
                "context": context,
            }
            actual = json.loads(session.request(payload))
            oracle = run_adapter(payload)
            assert oracle.returncode == 0, oracle.stderr
            assert actual == json.loads(oracle.stdout)
            assert session.start() == generation
            assert session.pid == pid
        image.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>two</text></svg>')
        payload = {"markdown": "![图](image.svg)", "options": {}, "context": context}
        assert json.loads(session.request(payload)) == json.loads(run_adapter(payload).stdout)
    finally:
        session.close()


def test_invalid_request_does_not_kill_server_or_pollute_next_response():
    session = RendererSession(require_node(), renderer_v2.require_artifact())
    try:
        session.start()
        pid = session.pid
        rejected = json.loads(session.request({"markdown": 42}))
        assert rejected["error"]["code"] == "invalid_request"
        accepted = json.loads(session.request({"markdown": "# after error"}))
        assert accepted["ok"] is True
        assert session.pid == pid
    finally:
        session.close()


def test_all_markdown_fixtures_match_one_shot_in_one_session(tmp_path: Path):
    session = RendererSession(require_node(), renderer_v2.require_artifact())
    fixtures = sorted((ROOT / "tests" / "fixtures" / "markdown").rglob("*.md"))
    assert len(fixtures) >= 20
    try:
        session.start()
        pid = session.pid
        for source in fixtures:
            payload = {
                "markdown": source.read_text(encoding="utf-8"),
                "options": {"fetch_remote_resources": False},
                "context": {
                    "source_path": str(source),
                    "output_path": str(tmp_path / source.with_suffix(".html").name),
                },
            }
            oracle = run_adapter(payload)
            assert oracle.returncode == 0, oracle.stderr
            assert json.loads(session.request(payload)) == json.loads(oracle.stdout), source
            assert session.pid == pid
    finally:
        session.close()


def test_asset_changes_and_warnings_are_not_hidden_by_previous_requests(tmp_path: Path):
    node = require_node()
    copied = tmp_path / "dist"
    shutil.copytree(Path(renderer_v2.require_artifact()).parent, copied)
    session = RendererSession(node, str(copied / "renderer.cjs"))
    payload = {"markdown": "$a^2$\n\n```mermaid\ngraph TD; A-->B;\n```"}
    try:
        session.start()
        before = json.loads(session.request(payload))
        assert before["resources"]["scripts"]
        css = copied / "katex" / "katex.min.css"
        css.write_text(css.read_text(encoding="utf-8") + "\n/* changed */", encoding="utf-8")
        (copied / "mermaid" / "metadata.json").write_text("{}", encoding="utf-8")
        for _ in range(2):
            actual = json.loads(session.request(payload))
            oracle = subprocess.run(
                [node, str(copied / "renderer.cjs")], input=json.dumps(payload),
                capture_output=True, text=True, encoding="utf-8", timeout=20,
            )
            assert oracle.returncode == 0, oracle.stderr
            assert actual == json.loads(oracle.stdout)
            assert actual["resources"]["scripts"] == []
            assert actual["resources"]["styles"][0]["css"].endswith("/* changed */")
            assert actual["warnings"]
    finally:
        session.close()


def test_packaging_smoke_uses_a_live_supported_bridge_entrypoint():
    node = require_node()
    spec = ROOT / "packaging" / "MarkdownReader.spec"
    tree = ast.parse(spec.read_text(encoding="utf-8"))
    assignment = next(
        statement for statement in tree.body
        if isinstance(statement, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_v2_smoke_source"
                for target in statement.targets)
    )
    # Execute only the spec's self-contained command construction, never PyInstaller.
    namespace: dict[str, object] = {"bundled_node": Path(node)}
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), str(spec), "exec"), namespace)
    source = namespace["_v2_smoke_source"]
    assert isinstance(source, str)
    completed = subprocess.run(
        [sys.executable, "-c", source], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", timeout=20,
    )
    assert completed.returncode == 0, completed.stderr


def test_close_reaps_child_threads_and_allows_explicit_restart():
    session = RendererSession(require_node(), renderer_v2.require_artifact())
    try:
        first = session.start()
        session.request({"markdown": "# close"})
        child = session._process
        threads = list(session._threads)
        assert child is not None
        session.close()
        session.close()
        assert child.poll() == 0
        assert session.pid is None
        assert all(not thread.is_alive() for thread in threads)
        assert session.start() > first
        assert json.loads(session.request({"markdown": "reopened"}))["ok"] is True
    finally:
        session.close()


def test_dead_child_is_recreated_with_a_fresh_smoke(monkeypatch):
    require_node()
    validations = []
    original = renderer_v2._invoke_artifact

    def observe(*args, **kwargs):
        validations.append(kwargs["runtime_validation"])
        return original(*args, **kwargs)

    monkeypatch.setattr(renderer_v2, "_invoke_artifact", observe)
    renderer_node.render_markdown_node("# before")
    session = renderer_v2._DEFAULT_BRIDGE._session
    assert session is not None and session._process is not None
    generation = session.start()
    session._process.terminate()
    session._process.wait(timeout=5)
    result = renderer_node.render_markdown_node("# after")
    assert "after</h1>" in result["html"]
    assert session.start() > generation
    assert validations == [True, True]


def test_timeout_covers_a_blocked_write_and_reaps_the_child(tmp_path: Path):
    script = tmp_path / "not-reading.cjs"
    script.write_text("setInterval(() => {}, 1000);", encoding="utf-8")
    session = RendererSession(require_node(), str(script), timeout=0.3)
    try:
        session.start()
        child = session._process
        threads = list(session._threads)
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="已超时"):
            session.request({"markdown": "x" * 2_000_000})
        assert time.monotonic() - started < 5
        assert child is not None and child.poll() is not None
        assert all(not thread.is_alive() for thread in threads)
        assert session.pid is None
    finally:
        session.close()


@pytest.mark.parametrize("reply, message", [
    ("not json", "Expecting value"),
    ('{"protocol":9,"id":"1","response":{}}', "传输协议"),
    ('{"protocol":1,"id":"wrong","response":{}}', "ID"),
    ('{"protocol":1,"id":"1"}', "response"),
])
def test_bad_frames_and_large_stderr_fail_boundedly(tmp_path: Path, reply: str, message: str):
    script = tmp_path / "bad-response.cjs"
    script.write_text(
        'require("readline").createInterface({input:process.stdin}).on("line", () => {'
        'process.stderr.write("diagnostic".repeat(20000));'
        f"process.stdout.write({json.dumps(reply + chr(10))});"
        "});",
        encoding="utf-8",
    )
    session = RendererSession(require_node(), str(script), timeout=5)
    try:
        session.start()
        with pytest.raises(RuntimeError, match=message) as error:
            session.request({"markdown": "# x"})
        assert "diagnostic" in str(error.value)
        assert len(str(error.value)) < 34_000
        assert session.pid is None
    finally:
        session.close()
