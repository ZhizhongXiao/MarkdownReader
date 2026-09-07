"""Build a deterministic, read-only conversion plan before rendering files."""

from __future__ import annotations

import os
from collections.abc import Iterable

MARKDOWN_EXTENSIONS = {".md", ".markdown"}


def is_markdown_path(path: str) -> bool:
    """Return whether *path* uses a supported Markdown extension."""
    return os.path.splitext(path)[1].lower() in MARKDOWN_EXTENSIONS


def _path_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _display_path(path: str) -> str:
    return os.path.normpath(path).replace("\\", "/")


def collect_input_documents(paths: Iterable[str]) -> tuple[list[dict], list[str], list[str]]:
    """Expand file and directory inputs into unique Markdown documents.

    Returns ``(documents, warnings, errors)``. Each document records the direct
    input that introduced it so the GUI can remove a whole directory source in
    one action.
    """
    documents_by_key: dict[str, dict] = {}
    warnings: list[str] = []
    errors: list[str] = []

    for raw_path in paths:
        raw = str(raw_path or "").strip().strip('"')
        if not raw:
            continue
        input_path = os.path.abspath(os.path.normpath(raw))

        if os.path.isfile(input_path):
            if not is_markdown_path(input_path):
                warnings.append(f"已忽略非 Markdown 文件：{input_path}")
                continue
            key = _path_key(input_path)
            documents_by_key[key] = {
                "source_path": input_path,
                "input_path": input_path,
                "origin": "selected",
            }
            continue

        if os.path.isdir(input_path):
            found = 0
            for root, dirs, files in os.walk(input_path):
                dirs.sort(key=str.casefold)
                for filename in sorted(files, key=str.casefold):
                    source_path = os.path.join(root, filename)
                    if not is_markdown_path(source_path):
                        continue
                    found += 1
                    key = _path_key(source_path)
                    existing = documents_by_key.get(key)
                    if existing and existing["origin"] == "selected":
                        continue
                    documents_by_key[key] = {
                        "source_path": os.path.abspath(source_path),
                        "input_path": input_path,
                        "origin": "directory",
                    }
            if found == 0:
                warnings.append(f"目录中未找到 Markdown 文件：{input_path}")
            continue

        errors.append(f"输入路径不存在：{input_path}")

    documents = sorted(
        documents_by_key.values(), key=lambda item: _display_path(item["source_path"]).casefold()
    )
    return documents, warnings, errors


def _common_source_root(documents: list[dict], raw_paths: list[str]) -> str | None:
    if not documents:
        return None

    normalized_inputs = [
        os.path.abspath(os.path.normpath(str(path).strip().strip('"')))
        for path in raw_paths
        if str(path or "").strip()
    ]
    if len(normalized_inputs) == 1 and os.path.isdir(normalized_inputs[0]):
        return normalized_inputs[0]

    parents = [os.path.dirname(item["source_path"]) for item in documents]
    try:
        return os.path.commonpath(parents)
    except ValueError:
        return None


def build_conversion_plan(
    paths: Iterable[str],
    output_dir: str,
    preserve_structure: bool = False,
) -> dict:
    """Return a serializable conversion plan without writing output files."""
    raw_paths = [str(path) for path in paths if str(path or "").strip()]
    documents, warnings, errors = collect_input_documents(raw_paths)
    output_root = os.path.abspath(os.path.normpath(output_dir or "output"))
    source_root = _common_source_root(documents, raw_paths)

    normalized_inputs = [
        os.path.abspath(os.path.normpath(path.strip().strip('"'))) for path in raw_paths
    ]
    single_directory = len(normalized_inputs) == 1 and os.path.isdir(normalized_inputs[0])
    actual_output_dir = output_root
    if preserve_structure and single_directory:
        source_name = os.path.basename(os.path.normpath(normalized_inputs[0]))
        if source_name:
            actual_output_dir = os.path.join(output_root, f"{source_name}-HTML")

    if preserve_structure and len(documents) > 1 and source_root is None:
        errors.append("所选文件没有共同源目录，无法保留目录结构。请分批选择同一资料目录。")
    if preserve_structure and not single_directory and source_root:
        drive, _tail = os.path.splitdrive(source_root)
        drive_root = drive + os.sep if drive else os.path.abspath(os.sep)
        if os.path.normcase(source_root) == os.path.normcase(drive_root):
            errors.append("所选文件的共同目录仅为磁盘根目录，无法安全保留目录结构。请分批选择。")

    items: list[dict] = []
    outputs: dict[str, str] = {}
    for index, document in enumerate(documents):
        source_path = document["source_path"]
        if preserve_structure and source_root:
            relative_source = os.path.relpath(source_path, source_root)
            output_relative = os.path.splitext(relative_source)[0] + ".html"
        else:
            relative_source = (
                os.path.relpath(source_path, source_root)
                if source_root
                else os.path.basename(source_path)
            )
            output_relative = os.path.splitext(os.path.basename(source_path))[0] + ".html"

        output_path = os.path.abspath(os.path.join(actual_output_dir, output_relative))
        output_key = _path_key(output_path)
        previous = outputs.get(output_key)
        if previous and _path_key(previous) != _path_key(source_path):
            errors.append(
                "输出文件冲突："
                f"{previous} 与 {source_path} 都将写入 {output_path}。"
                "请启用“保留目录结构”或调整文件名。"
            )
        else:
            outputs[output_key] = source_path

        items.append(
            {
                "id": str(index),
                "source_path": source_path,
                "input_path": document["input_path"],
                "relative_path": _display_path(relative_source),
                "output_path": output_path,
                "output_relative": _display_path(os.path.relpath(output_path, actual_output_dir)),
                "origin": document["origin"],
                "status": "pending",
                "warnings": [],
            }
        )

    direct_count = sum(item["origin"] == "selected" for item in items)
    directory_count = sum(item["origin"] == "directory" for item in items)
    return {
        "inputs": normalized_inputs,
        "items": items,
        "source_root": source_root or "",
        "output_dir": actual_output_dir,
        "warnings": warnings,
        "errors": list(dict.fromkeys(errors)),
        "counts": {
            "selected": direct_count,
            "directory": directory_count,
            "dependency": 0,
            "total": len(items),
        },
    }


def document_output_map(plan: dict) -> dict[str, str]:
    """Return the source-to-output mapping consumed by the Node renderer."""
    return {
        os.path.abspath(item["source_path"]): os.path.abspath(item["output_path"])
        for item in plan.get("items", [])
    }
