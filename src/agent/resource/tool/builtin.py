"""内置工具：与业务无关、所有 ReAct Agent 通用。

目前只有一个 ``terminate``：Agent 在决定"我已经得到最终答案"时显式调用，
让 ReAct 主循环跳出。把它作为显式 tool 而不是"特殊 token"有两点好处：
- LLM 的接口一致：一直是 {"tool": ..., "args": ...} 结构；
- 便于前端/日志统一渲染"终止步骤"。
"""

from __future__ import annotations

from typing import Any

from src.agent.resource.tool.base import BaseTool, ToolParameter, ToolResult

TERMINATE_TOOL_NAME = "terminate"


class TerminateTool(BaseTool):
    name = TERMINATE_TOOL_NAME
    description = "当已获得最终答案，或判定无法继续时，调用此工具结束任务。"
    parameters = [
        ToolParameter(
            name="final_answer",
            type="string",
            description="给用户的最终回复文本。",
            required=True,
        ),
    ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        final_answer = str(kwargs.get("final_answer") or "").strip()
        return ToolResult(
            content=final_answer,
            data={"final_answer": final_answer},
            is_final=True,
        )
