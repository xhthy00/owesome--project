"""AWEL 算子基类与 Agent 包装算子。

MapOperator 是 DAG 节点的最小形态：``async map(input) -> output``。
WrappedAgentOperator 把一个 ConversableAgent 包成 DAG 节点，输入/输出统一
是 AgentGenerateContext——这让"上一个 Agent 的回复"自然成为"下一个 Agent
的输入消息"，无需手动在节点间转换数据结构。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from src.agent.core.agent import AgentGenerateContext, AgentMessage
from src.agent.core.base_agent import ConversableAgent

IN = TypeVar("IN")
OUT = TypeVar("OUT")


class MapOperator(ABC, Generic[IN, OUT]):
    """单输入单输出的 DAG 算子。"""

    name: str = ""

    def __init__(self, name: str | None = None) -> None:
        if name is not None:
            self.name = name
        if not self.name:
            self.name = type(self).__name__

    @abstractmethod
    async def map(self, input_value: IN) -> OUT:
        raise NotImplementedError


class WrappedAgentOperator(MapOperator[AgentGenerateContext, AgentGenerateContext]):
    """把 ConversableAgent 挂到 DAG 上。

    职责：
    - 从入参 context 拿 message + rely_messages + sender，调 agent.generate_reply；
    - 把产出的 reply 覆盖 context.message，并更新 last_speaker；
    - 把本轮输入消息顺延加入 rely_messages，供下游节点参考上下文。
    """

    def __init__(self, agent: ConversableAgent, name: str | None = None) -> None:
        super().__init__(name=name or agent.name)
        self.agent = agent

    async def map(self, input_value: AgentGenerateContext) -> AgentGenerateContext:
        ctx = input_value
        if ctx.message is None:
            raise ValueError(
                f"[{self.name}] input context has no message; "
                f"cannot invoke agent without a received message."
            )

        sender: Any = ctx.last_speaker or ctx.sender
        reply: AgentMessage = await self.agent.generate_reply(
            received_message=ctx.message,
            sender=sender,
            reviewer=ctx.reviewer,
            rely_messages=list(ctx.rely_messages),
        )

        next_rely = list(ctx.rely_messages)
        if ctx.message.content:
            next_rely.append(ctx.message)

        return AgentGenerateContext(
            message=reply,
            sender=ctx.sender,
            reviewer=ctx.reviewer,
            memory=ctx.memory,
            rely_messages=next_rely,
            last_speaker=self.agent,
            llm_client=ctx.llm_client,
            extra=dict(ctx.extra),
        )
