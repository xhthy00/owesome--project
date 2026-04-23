"""Agent 核心数据结构：消息、评审信息、DAG 上下文。

这些类型构成 Agent 间通信的"协议层"，尽量保持最小且不耦合具体实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agent.core.action.base import ActionOutput
    from src.agent.core.memory.agent_memory import AgentMemory


@dataclass
class AgentReviewInfo:
    """一次 review 的结论。"""

    approve: bool = True
    comments: str | None = None


@dataclass
class AgentMessage:
    """Agent 间传递的最小消息体。

    与 LLM chat message 的区别：本结构同时承载 action 产物、评审结论、上下文，
    面向 Agent-to-Agent 协作，而非单轮 LLM 调用。
    """

    content: str | None = None
    current_goal: str | None = None
    action_report: "ActionOutput | None" = None
    review_info: AgentReviewInfo | None = None
    context: dict[str, Any] = field(default_factory=dict)
    rounds: int = 0
    role: str = "user"
    sender: str | None = None
    model_name: str | None = None


@dataclass
class AgentGenerateContext:
    """AWEL DAG 节点间流转的上下文对象。

    下游 WrappedAgentOperator 从中取出 message/sender/memory 等，执行完后
    覆盖 ``message``（及可选 ``last_speaker``），再交给下一个节点。
    """

    message: AgentMessage | None
    sender: Any  # 发送者 Agent（保持松耦合，不强制类型）
    reviewer: Any | None = None
    memory: "AgentMemory | None" = None
    rely_messages: list[AgentMessage] = field(default_factory=list)
    last_speaker: Any | None = None
    llm_client: Any = None
    extra: dict[str, Any] = field(default_factory=dict)
