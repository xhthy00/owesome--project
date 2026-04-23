"""EchoAgent：把 LLM 的输出原样回显。

价值：作为最小可跑的 ConversableAgent 实例，用于验证主循环、单元测试、
以及未来 AWEL DAG 的连通性冒烟。不具备任何业务能力。
"""

from __future__ import annotations

from typing import Any

from src.agent.core.action.base import Action, ActionOutput
from src.agent.core.base_agent import ConversableAgent
from src.agent.core.profile import ProfileConfig


class EchoAction(Action):
    name = "echo"

    async def run(self, ai_message: str, **kwargs: Any) -> ActionOutput:
        return ActionOutput(
            content=ai_message,
            is_exe_success=True,
            action=self.name,
            observations=ai_message,
        )


class EchoAgent(ConversableAgent):
    profile = ProfileConfig(
        name="Echo",
        role="EchoBot",
        goal="把用户的问题原样复述一遍。",
    )
    actions = [EchoAction()]
