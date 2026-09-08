"""Vendor tool-call text normalization helpers."""

from __future__ import annotations

import json
import re
from typing import Any

_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.DOTALL | re.IGNORECASE)
_MINIMAX_INVOKE_RE = re.compile(
    r"<invoke\b[^>]*\bname\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</invoke>",
    re.DOTALL | re.IGNORECASE,
)
_MINIMAX_TOOL_RE = re.compile(
    r"<tool\b[^>]*\bname\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</tool>",
    re.DOTALL | re.IGNORECASE,
)
_MINIMAX_SELF_CLOSING_TOOL_RE = re.compile(
    r"<tool\b[^>]*\bname\s*=\s*[\"']([^\"']+)[\"'][^>]*/>",
    re.DOTALL | re.IGNORECASE,
)
_MINIMAX_PARAM_RE = re.compile(
    r"<parameter\b[^>]*\bname\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</parameter>",
    re.DOTALL | re.IGNORECASE,
)
_MINIMAX_ARGUMENTS_RE = re.compile(
    r"<arguments\b[^>]*>(.*?)</arguments>",
    re.DOTALL | re.IGNORECASE,
)
_MINIMAX_INVOKE_OPEN_RE = re.compile(
    r"<invoke\b[^>]*\bname\s*=\s*[\"']([^\"']+)[\"'][^>]*>",
    re.DOTALL | re.IGNORECASE,
)
# MiniMax M2 常用 `<args>` + 裸 JSON 的参数方言，且经常把开标签写坏成
# `<args": {`（引号/冒号混进标签、`>` 缺失）。本正则同时容忍完整与畸形的
# 开标签，匹配停在 JSON 起始的 `{` 之前。`<args\b` 不会误吞 `<arguments>`。
_MINIMAX_ARGS_TAG_RE = re.compile(r"<args\b[\"']?\s*:?\s*>?\s*", re.IGNORECASE)


def strip_think_blocks(text: str) -> str:
    return _THINK_BLOCK_RE.sub("", str(text or "")).strip()


def looks_like_minimax_tool_xml(text: str) -> bool:
    blob = str(text or "").lower()
    return "<minimax:tool_call" in blob or "<invoke" in blob or "<tool_call" in blob


def _decode_parameter_value(value: str) -> Any:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return raw


def _parse_args_json_tag(text: str) -> dict[str, Any] | None:
    """提取 ``<args>`` 标记之后**天然完整**的 JSON 对象。

    只接受真实闭合的 JSON：被截断的输出返回 ``None``，交给上层截断分支
    处理——猜测补全残缺参数再去执行工具，可能悄悄执行写了一半的 SQL。
    """
    decoder = json.JSONDecoder()
    for tag in _MINIMAX_ARGS_TAG_RE.finditer(text or ""):
        rest = text[tag.end():].lstrip()
        if not rest.startswith("{"):
            continue
        try:
            parsed, _ = decoder.raw_decode(rest)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _parse_args(body: str) -> dict[str, Any] | None:
    args: dict[str, Any] = {}
    for match in _MINIMAX_PARAM_RE.finditer(body or ""):
        name = (match.group(1) or "").strip()
        if name:
            args[name] = _decode_parameter_value(match.group(2) or "")
    if args:
        return args

    arguments = _MINIMAX_ARGUMENTS_RE.search(body or "")
    if arguments:
        value = _decode_parameter_value(arguments.group(1) or "")
        return value if isinstance(value, dict) else None

    json_args = _parse_args_json_tag(body or "")
    if json_args is not None:
        return json_args
    return {}


def parse_minimax_tool_call(raw_text: str) -> dict[str, Any] | None:
    """Parse the first complete MiniMax tool call from supported XML dialects."""
    text = str(raw_text or "")
    if not looks_like_minimax_tool_xml(text):
        return None

    match = _MINIMAX_INVOKE_RE.search(text)
    if match is None:
        match = _MINIMAX_TOOL_RE.search(text)
    if match is not None:
        tool_name = (match.group(1) or "").strip()
        args = _parse_args(match.group(2) or "")
        if tool_name and args is not None:
            return {"tool": tool_name, "args": args}

    self_closing = _MINIMAX_SELF_CLOSING_TOOL_RE.search(text)
    if self_closing:
        tool_name = (self_closing.group(1) or "").strip()
        if tool_name:
            return {"tool": tool_name, "args": {}}

    # `<invoke name="...">` 开标签在、`</invoke>` 没等到（响应被截断时的常见
    # 形态）：只要 `<args>` 里的 JSON 本身天然完整，这次调用仍可还原。
    open_tag = _MINIMAX_INVOKE_OPEN_RE.search(text)
    if open_tag is not None:
        tool_name = (open_tag.group(1) or "").strip()
        json_args = _parse_args_json_tag(text[open_tag.end():])
        if tool_name and json_args is not None:
            return {"tool": tool_name, "args": json_args}
    return None


__all__ = [
    "looks_like_minimax_tool_xml",
    "parse_minimax_tool_call",
    "strip_think_blocks",
]
