"""ChatAwelTeam：team 模式下的轻量路由决策器。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ChatAwelTeam:
    """当前仅承载 ToolAgent 开关，后续可平滑扩到更多 DAG 分支开关。"""

    enable_tool_agent: bool = True

    def resolve_sub_task_agent(self, planned_agent: str) -> str:
        """根据开关把 Planner 规划的 agent 归一化为最终执行者。"""
        if planned_agent == "ToolExpert" and self.enable_tool_agent:
            return "ToolExpert"
        return "DataAnalyst"


def build_chat_team(*, enable_tool_agent: bool = True) -> ChatAwelTeam:
    """构造 team 运行时配置。Phase F 关键开关：ToolAgent 是否参与 DAG。"""
    return ChatAwelTeam(enable_tool_agent=enable_tool_agent)

