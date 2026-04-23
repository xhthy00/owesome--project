"""函数签名内省：把一个普通 Python 函数映射为 Tool 的参数 schema。

规则：
- 参数名、类型注解、默认值、docstring 各取所长：
  * 参数名 -> ToolParameter.name
  * 类型注解 -> ToolParameter.type（映射到 "string"/"integer"/"number"/"boolean"/"array"/"object"）
  * 无默认值 -> required=True
  * docstring 的 ``Args:`` 段为每个参数补 description
- 跳过 ``self`` / ``cls``；跳过 ``**kwargs`` / ``*args``。
- ``Optional[T]`` / ``T | None`` 视为 T，required 由默认值决定，而非 Optional。
"""

from __future__ import annotations

import inspect
import re
import types
import typing
from typing import Any

_PY_TYPE_TO_JSON: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    tuple: "array",
    dict: "object",
}


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    """展开 ``Optional[T]`` / ``T | None`` -> (T, is_optional)。"""
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        is_optional = len(args) < len(typing.get_args(annotation))
        if len(args) == 1:
            return args[0], is_optional
        return typing.Union[tuple(args)], is_optional  # type: ignore[return-value]
    return annotation, False


def _annotation_to_json_type(annotation: Any) -> str:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return "string"
    inner, _ = _unwrap_optional(annotation)
    origin = typing.get_origin(inner) or inner
    if isinstance(origin, type) and origin in _PY_TYPE_TO_JSON:
        return _PY_TYPE_TO_JSON[origin]
    if isinstance(inner, type) and inner in _PY_TYPE_TO_JSON:
        return _PY_TYPE_TO_JSON[inner]
    return "string"


_ARGS_SECTION_RE = re.compile(
    r"(?:Args|Arguments|Params|Parameters)\s*:\s*\n(?P<body>(?:.+\n?)+?)(?=\n\s*\n|\n\S|\Z)",
    re.IGNORECASE,
)
_ARG_LINE_RE = re.compile(r"^\s*(\w+)\s*(?:\([^)]*\))?\s*:\s*(.+?)\s*$")


def _parse_args_doc(doc: str | None) -> dict[str, str]:
    """从 docstring 里抽 ``Args:`` 段，返回 {arg_name: description}。"""
    if not doc:
        return {}
    m = _ARGS_SECTION_RE.search(doc)
    if not m:
        return {}
    body = m.group("body")
    out: dict[str, str] = {}
    current_name: str | None = None
    for line in body.splitlines():
        lm = _ARG_LINE_RE.match(line)
        if lm:
            current_name = lm.group(1)
            out[current_name] = lm.group(2).strip()
        elif current_name and line.strip():
            out[current_name] += " " + line.strip()
    return out


def _short_description(doc: str | None) -> str:
    if not doc:
        return ""
    first = doc.strip().split("\n\n", 1)[0]
    return " ".join(line.strip() for line in first.splitlines() if line.strip())


def parse_function_schema(fn: Any) -> dict[str, Any]:
    """把函数反射成 ``{name, description, parameters: [...]}`` 的 schema。

    parameters 中每项：``{name, type, description, required, default}``。
    """
    sig = inspect.signature(fn)
    try:
        hints = typing.get_type_hints(fn)
    except Exception:  # pragma: no cover - 类型注解解析失败时退化
        hints = {}
    arg_docs = _parse_args_doc(inspect.getdoc(fn))
    description = _short_description(inspect.getdoc(fn))

    parameters: list[dict[str, Any]] = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        annotation = hints.get(name, param.annotation)
        _, optional_by_type = _unwrap_optional(annotation)
        has_default = param.default is not inspect.Parameter.empty
        required = not (optional_by_type or has_default)

        parameters.append(
            {
                "name": name,
                "type": _annotation_to_json_type(annotation),
                "description": arg_docs.get(name, ""),
                "required": required,
                "default": None if not has_default else param.default,
            }
        )

    return {
        "name": getattr(fn, "__name__", "anonymous"),
        "description": description,
        "parameters": parameters,
    }
