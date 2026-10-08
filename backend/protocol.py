"""Versioned service requests, independent of any IPC transport."""

from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

PROTOCOL_VERSION = 1


class BackendError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ErrorDetail(TypedDict):
    code: str
    message: str


class Response(TypedDict):
    protocol: Literal[1]
    id: str | None
    ok: bool
    result: NotRequired[dict[str, object]]
    error: NotRequired[ErrorDetail]


@dataclass(frozen=True)
class Request:
    id: str
    method: Literal["status", "convert"]
    params: dict[str, object]


@dataclass(frozen=True)
class ConvertParams:
    input_path: str
    output_path: str | None
    overwrite: bool | None
    offline: bool


def parse_request(value: object) -> Request:
    if not isinstance(value, dict):
        raise BackendError("invalid_request", "请求必须是 JSON 对象。")
    if type(value.get("protocol")) is not int or value["protocol"] != PROTOCOL_VERSION:
        raise BackendError("unsupported_protocol", "Backend protocol 必须为 1。")
    request_id = value.get("id")
    if not isinstance(request_id, str) or not request_id:
        raise BackendError("invalid_request", "id 必须为非空字符串。")
    raw_params = value.get("params", {})
    if not isinstance(raw_params, dict):
        raise BackendError("invalid_params", "params 必须是对象。")
    params: dict[str, object] = {}
    for key, item in raw_params.items():
        if not isinstance(key, str):
            raise BackendError("invalid_params", "params 的键必须是字符串。")
        params[key] = item
    method = value.get("method")
    if method == "status":
        if params:
            raise BackendError("invalid_params", "status 不接受参数。")
        return Request(request_id, "status", params)
    if method == "convert":
        return Request(request_id, "convert", params)
    raise BackendError("unknown_method", "只支持 status 和 convert。")


def parse_convert_params(params: dict[str, object]) -> ConvertParams:
    unknown = params.keys() - {"input_path", "output_path", "overwrite", "offline"}
    if unknown:
        raise BackendError("invalid_params", f"未知转换参数：{', '.join(sorted(unknown))}")
    input_path = params.get("input_path")
    output_path = params.get("output_path")
    overwrite = params.get("overwrite")
    offline = params.get("offline", False)
    if not isinstance(input_path, str) or not input_path.strip():
        raise BackendError("invalid_params", "input_path 必须为非空字符串。")
    if output_path is not None and (not isinstance(output_path, str) or not output_path.strip()):
        raise BackendError("invalid_params", "output_path 必须为非空字符串。")
    if overwrite is not None and not isinstance(overwrite, bool):
        raise BackendError("invalid_params", "overwrite 必须为布尔值。")
    if not isinstance(offline, bool):
        raise BackendError("invalid_params", "offline 必须为布尔值。")
    return ConvertParams(input_path, output_path, overwrite, offline)
