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
    return None


__all__ = [
    "looks_like_minimax_tool_xml",
    "parse_minimax_tool_call",
    "strip_think_blocks",
]
