"""LinearDAG + WrappedAgentOperator 串联冒烟测试。

场景：把两个 EchoAgent 串成链，验证：
- 第二节点的"received_message"是第一节点的回复；
- rely_messages 正确累积；
- last_speaker 指向末端 Agent。
"""

from __future__ import annotations

import asyncio

import pytest

from src.agent.awel.dag import LinearDAG
from src.agent.awel.operator import MapOperator, WrappedAgentOperator
from src.agent.core.agent import AgentGenerateContext, AgentMessage
from src.agent.expand.echo_agent import EchoAgent
from src.agent.expand.user_proxy import UserProxyAgent


class FakeLlmClient:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[list[dict[str, str]]] = []

    async def chat(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        if not self._replies:
            return ""
        if len(self._replies) == 1:
            return self._replies[0]
        return self._replies.pop(0)


def _run(coro):
    return asyncio.run(coro)


def test_two_echo_agents_pipe_messages_in_order():
    llm1 = FakeLlmClient(["first reply"])
    llm2 = FakeLlmClient(["second reply"])
    agent1 = EchoAgent(llm_client=llm1)
    agent2 = EchoAgent(llm_client=llm2)

    dag = LinearDAG(
        [
            WrappedAgentOperator(agent1, name="A1"),
            WrappedAgentOperator(agent2, name="A2"),
        ],
        name="echo-chain",
    )

    initial_ctx = AgentGenerateContext(
        message=AgentMessage(content="user question", role="user"),
        sender=UserProxyAgent(),
    )

    final_ctx = _run(dag.execute(initial_ctx))

    assert final_ctx.message is not None
    assert final_ctx.message.content == "second reply"
    assert final_ctx.last_speaker is agent2

    assert len(llm2.calls) == 1
    second_user_msg = llm2.calls[0][-1]
    assert second_user_msg["role"] == "user"
    assert "first reply" in second_user_msg["content"]

    assert len(final_ctx.rely_messages) == 2
    assert final_ctx.rely_messages[0].content == "user question"
    assert final_ctx.rely_messages[1].content == "first reply"


def test_linear_dag_rejects_empty_operators():
    with pytest.raises(ValueError):
        LinearDAG([])


def test_wrapped_agent_operator_raises_on_missing_message():
    agent = EchoAgent(llm_client=FakeLlmClient(["x"]))
    op = WrappedAgentOperator(agent)
    ctx = AgentGenerateContext(message=None, sender=UserProxyAgent())
    with pytest.raises(ValueError):
        _run(op.map(ctx))


def test_custom_map_operator_can_mix_in_chain():
    class UppercaseOp(MapOperator[AgentGenerateContext, AgentGenerateContext]):
        async def map(self, input_value):
            msg = input_value.message
            if msg and msg.content:
                msg.content = msg.content.upper()
            return input_value

    llm = FakeLlmClient(["final"])
    agent = EchoAgent(llm_client=llm)

    dag = LinearDAG(
        [
            UppercaseOp(name="upper"),
            WrappedAgentOperator(agent, name="echo"),
        ]
    )
    ctx = AgentGenerateContext(
        message=AgentMessage(content="hello", role="user"),
        sender=UserProxyAgent(),
    )
    final_ctx = _run(dag.execute(ctx))

    user_msg = llm.calls[0][-1]
    assert "HELLO" in user_msg["content"]
    assert final_ctx.message.content == "final"


def test_dag_repr_shows_pipeline():
    agent = EchoAgent(llm_client=FakeLlmClient(["x"]))
    dag = LinearDAG(
        [WrappedAgentOperator(agent, name="A"), WrappedAgentOperator(agent, name="B")],
        name="mychain",
    )
    assert "A >> B" in repr(dag)
