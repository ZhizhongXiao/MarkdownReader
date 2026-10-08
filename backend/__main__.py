"""Headless entry point: python -m backend status|convert|serve."""

import argparse
import json
import logging
import os
import sys
import uuid

from backend.named_pipe import DEFAULT_PIPE_NAME, NamedPipeServer
from backend.service import Backend


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MarkdownReader 无 GUI 转换宿主")
    parser.add_argument("--verbose", action="store_true", help="向 stderr 输出分阶段计时")
    commands = parser.add_subparsers(dest="method", required=True)
    commands.add_parser("status", help="报告宿主状态，不启动 Node")
    convert = commands.add_parser("convert", help="将单个 Markdown 转换为 standalone HTML")
    convert.add_argument("input_path")
    convert.add_argument("--output", help="输出文件；默认与 Markdown 同目录、同名 .html")
    convert.add_argument("--config", help="指定配置文件；默认使用 MDR profile")
    convert.add_argument("--overwrite", action=argparse.BooleanOptionalAction, default=None)
    convert.add_argument("--offline", action="store_true", help="关闭远程资源抓取")
    serve = commands.add_parser("serve", help="通过本机 Named Pipe 提供 Backend 服务")
    serve.add_argument("--config", help="指定配置文件；默认使用 MDR profile")
    serve.add_argument("--pipe-name", default=DEFAULT_PIPE_NAME, help="本机 LOCAL 管道名称")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s", stream=sys.stderr,
    )
    params: dict[str, object] = {}
    config_path = None
    if args.method == "serve":
        config_path = args.config
        with Backend(config_path=config_path) as backend:
            NamedPipeServer(args.pipe_name).serve_until_shutdown(backend)
        return 0
    if args.method == "convert":
        params = {"input_path": os.path.abspath(args.input_path), "offline": args.offline}
        if args.output is not None:
            params["output_path"] = os.path.abspath(args.output)
        if args.overwrite is not None:
            params["overwrite"] = args.overwrite
        config_path = args.config
    with Backend(config_path=config_path) as backend:
        response = backend.handle_request({
            "protocol": 1, "id": uuid.uuid4().hex, "method": args.method, "params": params,
        })
    # ASCII JSON is valid UTF-8 even when stdout is redirected under a Windows code page.
    print(json.dumps(response, ensure_ascii=True))
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
