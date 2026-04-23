"""ConversableAgent 主循环单元测试。

覆盖：
- 单轮成功（thinking -> review -> act -> verify）
- review 失败触发重试，失败原因回灌下一轮 prompt
- correctness_check 失败触发重试
- 超过 max_retry 后返回失败 reply
- 短期记忆被写入
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.agent.core.action.base import Action, ActionOutput
from src.agent.core.agent import AgentMessage
from src.agent.core.base_agent import ConversableAgent
from src.agent.core.memory.agent_memory import AgentMemory
from src.agent.core.profile import ProfileConfig
from src.agent.expand.echo_agent import EchoAgent
from src.agent.expand.user_proxy import UserProxyAgent


class FakeLlmClient:
    """顺序吐出预设回复；超出则重复最后一条。"""

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


def test_echo_agent_single_round_success():
    llm = FakeLlmClient(["hello world"])
    agent = EchoAgent(llm_client=llm)

    reply = _run(
        agent.generate_reply(
            received_message=AgentMessage(content="ping", role="user"),
            sender=UserProxyAgent(),
        )
    )

    assert reply.content == "hello world"
    assert reply.action_report is not None
    assert reply.action_report.is_exe_success is True
    assert reply.action_report.action == "echo"
    assert reply.rounds == 1
    assert reply.sender == "Echo"
    assert len(llm.calls) == 1


def test_review_failure_triggers_retry_and_feeds_fail_reason_back():
    class PickyAgent(EchoAgent):
        def __init__(self, **kw):
            super().__init__(**kw)
            self._review_count = 0

        async def review(self, content: str, reviewer: Any) -> tuple[bool, str | None]:
            self._review_count += 1
            if self._review_count < 2:
                return False, "内容缺少问候语"
            return True, None

    llm = FakeLlmClient(["first try", "fixed reply"])
    agent = PickyAgent(llm_client=llm)

    reply = _run(
        agent.generate_reply(
            received_message=AgentMessage(content="你好", role="user"),
            sender=UserProxyAgent(),
        )
    )

    assert reply.content == "fixed reply"
    assert reply.rounds == 2
    assert len(llm.calls) == 2
    second_user = llm.calls[1][-1]
    assert second_user["role"] == "user"
    assert "上一轮失败原因" in second_user["content"]
    assert "内容缺少问候语" in second_user["content"]


def test_correctness_check_failure_triggers_retry():
    class LengthCheckAgent(EchoAgent):
        def __init__(self, **kw):
            super().__init__(**kw)
            self._checked = 0

        async def correctness_check(self, message):
            self._checked += 1
            if self._checked < 2:
                return False, "回答太短"
            return True, None

    llm = FakeLlmClient(["x", "xxxxxx"])
    agent = LengthCheckAgent(llm_client=llm)

    reply = _run(
        agent.generate_reply(
            received_message=AgentMessage(content="测试", role="user"),
            sender=UserProxyAgent(),
        )
    )

    assert reply.action_report.is_exe_success is True
    assert reply.rounds == 2
    assert agent._checked == 2


def test_exceeds_max_retry_returns_failed_reply():
    class AlwaysRejectAgent(EchoAgent):
        async def review(self, content: str, reviewer: Any):
            return False, "永远不满意"

    llm = FakeLlmClient(["a", "b", "c", "d"])
    agent = AlwaysRejectAgent(llm_client=llm, max_retry_count=3)

    reply = _run(
        agent.generate_reply(
            received_message=AgentMessage(content="q", role="user"),
            sender=UserProxyAgent(),
        )
    )

    assert reply.action_report is not None
    assert reply.action_report.is_exe_success is False
    assert reply.rounds == 3


def test_memory_is_written_on_success():
    memory = AgentMemory(max_size=10)
    llm = FakeLlmClient(["ok"])
    agent = EchoAgent(llm_client=llm, memory=memory)

    _run(
        agent.generate_reply(
            received_message=AgentMessage(content="hi", role="user"),
            sender=UserProxyAgent(),
        )
    )

    entries = _run(memory.read())
    assert len(entries) == 1
    assert entries[0]["agent"] == "Echo"
    assert entries[0]["question"] == "hi"
    assert entries[0]["is_success"] is True


def test_conversable_agent_without_actions_uses_llm_text_as_output():
    class PlainAgent(ConversableAgent):
        profile = ProfileConfig(name="Plain", role="Chatter")
        actions = []

    llm = FakeLlmClient(["just talk"])
    agent = PlainAgent(llm_client=llm)

    reply = _run(
        agent.generate_reply(
            received_message=AgentMessage(content="hello", role="user"),
            sender=UserProxyAgent(),
        )
    )
    assert reply.content == "just talk"
    assert reply.action_report.is_exe_success is True
    assert reply.action_report.content == "just talk"


def test_action_failure_triggers_retry_via_verify():
    class FlakyAction(Action):
        name = "flaky"

        def __init__(self) -> None:
            self.calls = 0

        async def run(self, ai_message: str, **kwargs: Any) -> ActionOutput:
            self.calls += 1
            if self.calls < 2:
                return ActionOutput(is_exe_success=False, content="first try failed", action=self.name)
            return ActionOutput(is_exe_success=True, content=ai_message, action=self.name)

    class FlakyAgent(ConversableAgent):
        profile = ProfileConfig(name="Flaky", role="Tester")

    flaky = FlakyAction()
    llm = FakeLlmClient(["r1", "r2"])
    agent = FlakyAgent(llm_client=llm, actions=[flaky])

    reply = _run(
        agent.generate_reply(
            received_message=AgentMessage(content="go", role="user"),
            sender=UserProxyAgent(),
        )
    )

    assert flaky.calls == 2
    assert reply.action_report.is_exe_success is True
    assert reply.rounds == 2


def test_missing_profile_raises():
    class Bad(ConversableAgent):
        pass

    with pytest.raises(ValueError):
        Bad()
