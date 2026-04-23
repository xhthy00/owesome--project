"""FunctionTool：把普通 Python 函数一键包成 Tool。

两种用法：
    # 1. 装饰器
    @tool(name="greet", description="打招呼")
    def greet(name: str) -> str:
        ...

    # 2. 显式构造
    FunctionTool(fn=greet, name="greet")

同步函数会自动用 ``asyncio.to_thread`` 包装；协程函数直接 await。
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable

from src.agent.resource.tool.base import BaseTool, ToolParameter, ToolResult
from src.agent.util.function_utils import parse_function_schema


class FunctionTool(BaseTool):
    def __init__(
        self,
        fn: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
        parameters: list[ToolParameter] | None = None,
    ) -> None:
        schema = parse_function_schema(fn)
        resolved_name = name or schema["name"]
        resolved_desc = description if description is not None else schema["description"]
        if parameters is None:
            parameters = [ToolParameter(**p) for p in schema["parameters"]]
        super().__init__(name=resolved_name, description=resolved_desc, parameters=parameters)
        self._fn = fn
        self._is_coro = inspect.iscoroutinefunction(fn)

    async def execute(self, **kwargs: Any) -> ToolResult:
        call_kwargs = self._filter_kwargs(kwargs)
        if self._is_coro:
            raw = await self._fn(**call_kwargs)
        else:
            raw = await asyncio.to_thread(self._fn, **call_kwargs)
        return self._normalize(raw)

    def _filter_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        allowed = {p.name for p in self.parameters}
        return {k: v for k, v in kwargs.items() if k in allowed}

    @staticmethod
    def _normalize(raw: Any) -> ToolResult:
        if isinstance(raw, ToolResult):
            return raw
        if isinstance(raw, str):
            return ToolResult(content=raw, data=raw)
        return ToolResult(content=str(raw), data=raw)


def tool(
    name: str | None = None,
    description: str | None = None,
    parameters: list[ToolParameter] | None = None,
) -> Callable[[Callable[..., Any]], FunctionTool]:
    """装饰器：把普通函数注册为 Tool。"""

    def decorator(fn: Callable[..., Any]) -> FunctionTool:
        return FunctionTool(fn=fn, name=name, description=description, parameters=parameters)

    return decorator
