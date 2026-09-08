"""容错 JSON 解析。

LLM 输出的 JSON 常常伴有 Markdown 代码块、前后噪声、或末尾逗号，直接
``json.loads`` 会失败。本模块按以下优先级尝试：

1. 提取 ```json ... ``` 或 ``` ... ``` 代码块；
2. 直接 ``json.loads``；
3. 检测到未闭合括号/字符串（输出被截断）时补齐闭合再解析；
4. 截取首个 ``{`` / ``[`` 到最后一个 ``}`` / ``]`` 之间的子串。

全部失败则抛 ``ValueError``。本函数只负责"尽力解析"，不做结构校验。
"""

from __future__ import annotations

import json
import re
from typing import Any

_CODE_BLOCK_RE = re.compile(r"```(?:json|JSON)?\s*(.+?)\s*```", re.DOTALL)
_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.DOTALL | re.IGNORECASE)


class JsonParseError(ValueError):
    """JSON parse failure with safe structural diagnostics."""

    def __init__(self, raw: str, *, likely_truncated: bool) -> None:
        self.raw_length = len(raw)
        self.preview = raw[:200]
        self.likely_truncated = likely_truncated
        super().__init__(
            f"Cannot parse JSON from diagnostic preview "
            f"(raw_length={self.raw_length}): {self.preview!r}"
        )


def _likely_truncated(raw: str) -> bool:
    if _repair_truncated(raw) is not None:
        return True
    lowered = raw.lower()
    if "<minimax:tool_call" in lowered and "</minimax:tool_call>" not in lowered:
        return True
    if "<invoke" in lowered and "</invoke>" not in lowered:
        return True
    if "<tool_call" in lowered and "</tool_call>" not in lowered:
        return True
    return False


def looks_structurally_truncated(text: str) -> bool:
    """Return whether JSON/XML delimiters indicate an incomplete model response."""
    return _likely_truncated(str(text or ""))


def _try_parse_one(raw: str) -> Any:
    m = _CODE_BLOCK_RE.search(raw)
    if m:
        candidate = m.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # 修复要排在子串扫描之前：形如 '{"tool": "x", "args": {}, "thou' 的截断输出里，
    # 扫描会先撞上内层那个完整的 {} 并把它当作结果返回，丢掉外层的 tool/args。
    # _repair_truncated 只在检测到未闭合括号/字符串时才返回内容，正常输入不受影响。
    repaired = _repair_truncated(raw)
    if repaired is not None:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(raw):
        if ch not in "{[":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw, idx)
            return parsed
        except json.JSONDecodeError:
            continue

    raise ValueError("no valid json found")


_TRAILING_PARTIAL_KEY_RE = re.compile(r",\s*\"[^\"]*\"?\s*:?\s*$")
_TRAILING_COMMA_RE = re.compile(r",\s*$")


def _repair_truncated(raw: str) -> str | None:
    """补全被 ``max_tokens`` 截断的 JSON：闭合未收尾的字符串与括号。

    截断是 ReAct 里最常见的一类格式失败（长 SQL / 长 args 写到一半就没了）。
    只做闭合、不猜测缺失的值——补出来的对象可能带残缺入参，交给工具自己报错，
    比整轮"无法解析 JSON"更有信息量。检测不到未闭合结构时返回 ``None``，
    保证正常输入走原有解析路径。
    """
    start = next((i for i, ch in enumerate(raw) if ch in "{["), None)
    if start is None:
        return None

    stack: list[str] = []
    in_str = False
    escaped = False
    for ch in raw[start:]:
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()

    if not stack and not in_str:
        return None  # 没有截断，失败另有原因

    patched = raw[start:]
    if escaped:
        patched = patched[:-1]
    if in_str:
        patched += '"'
    # 丢掉写了一半的键，例如 '{"a": 1, "b' -> '{"a": 1'
    patched = _TRAILING_PARTIAL_KEY_RE.sub("", patched)
    patched = _TRAILING_COMMA_RE.sub("", patched)
    for ch in reversed(stack):
        patched += "}" if ch == "{" else "]"
    return patched


def parse_json_tolerant(text: str) -> Any:
    if text is None or not str(text).strip():
        raise ValueError("empty text")

    raw = str(text)
    candidates = [raw]
    without_think = _THINK_BLOCK_RE.sub("", raw)
    if without_think != raw:
        candidates.append(without_think)

    for candidate in candidates:
        try:
            return _try_parse_one(candidate)
        except ValueError:
            continue

    raise JsonParseError(raw, likely_truncated=_likely_truncated(raw))


__all__ = ["JsonParseError", "looks_structurally_truncated", "parse_json_tolerant"]
