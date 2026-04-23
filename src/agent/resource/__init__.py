"""Agent 资源层：工具、数据源、知识库等外部能力的统一封装。

Phase B 只落地 Tool 子系统；后续 Phase C/D 再引入 Resource/ResourcePack
统一抽象（datasource / memory / knowledge 等一起挂进去）。
"""

from src.agent.resource.tool.base import BaseTool, ToolParameter, ToolResult
from src.agent.resource.tool.builtin import TerminateTool
from src.agent.resource.tool.business import (
    build_default_toolpack,
    default_business_tools,
)
from src.agent.resource.tool.function_tool import FunctionTool, tool
from src.agent.resource.tool.pack import ToolPack

__all__ = [
    "BaseTool",
    "FunctionTool",
    "TerminateTool",
    "ToolPack",
    "ToolParameter",
    "ToolResult",
    "build_default_toolpack",
    "default_business_tools",
    "tool",
]
