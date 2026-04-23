"""Agent 子系统：多 Agent 协作与 AWEL DAG 编排的核心入口。

对外仅暴露稳定 API，内部模块可自由迭代。
"""

from src.agent.adapter.llm_adapter import LangChainLlmClient
from src.agent.awel.dag import LinearDAG
from src.agent.awel.operator import MapOperator, WrappedAgentOperator
from src.agent.core.action.base import Action, ActionOutput
from src.agent.core.action.tool_action import ToolAction
from src.agent.core.agent import (
    AgentGenerateContext,
    AgentMessage,
    AgentReviewInfo,
)
from src.agent.core.base_agent import ConversableAgent, LlmClient
from src.agent.core.memory.agent_memory import AgentMemory
from src.agent.core.profile import ProfileConfig
from src.agent.core.react_agent import ReActAgent
from src.agent.expand.charter import ChartAction, CharterAgent
from src.agent.expand.data_analyst import DataAnalystAgent, build_data_analyst
from src.agent.expand.planner import PlanAction, PlannerAgent
from src.agent.expand.summarizer import SummarizerAgent
from src.agent.resource.tool.base import BaseTool, ToolParameter, ToolResult
from src.agent.resource.tool.builtin import TERMINATE_TOOL_NAME, TerminateTool
from src.agent.resource.tool.function_tool import FunctionTool, tool
from src.agent.resource.tool.pack import ToolPack

__all__ = [
    "Action",
    "ActionOutput",
    "AgentGenerateContext",
    "AgentMemory",
    "AgentMessage",
    "AgentReviewInfo",
    "BaseTool",
    "ChartAction",
    "CharterAgent",
    "ConversableAgent",
    "DataAnalystAgent",
    "FunctionTool",
    "LangChainLlmClient",
    "LinearDAG",
    "LlmClient",
    "MapOperator",
    "PlanAction",
    "PlannerAgent",
    "ProfileConfig",
    "ReActAgent",
    "SummarizerAgent",
    "TERMINATE_TOOL_NAME",
    "TerminateTool",
    "ToolAction",
    "ToolPack",
    "ToolParameter",
    "ToolResult",
    "WrappedAgentOperator",
    "build_data_analyst",
    "tool",
]
