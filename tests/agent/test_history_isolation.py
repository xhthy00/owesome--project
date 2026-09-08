import asyncio

from src.agent.core.agent import AgentMessage
from src.agent.core.base_agent import ConversableAgent
from src.agent.core.profile import ProfileConfig
from src.chat.service.agent_runner import _RunConstraints


class _Agent(ConversableAgent):
    profile = ProfileConfig(name="Test", role="tester")


def test_raw_conversation_history_is_not_injected_as_user_messages() -> None:
    agent = _Agent()
    received = AgentMessage(
        content="当前问题",
        role="user",
        context={
            "constraints": {
                "conversation_history": [
                    {"type": "human", "content": "旧问题"},
                    {"type": "ai", "content": "旧答案"},
                ]
            }
        },
    )
    reply = agent._init_reply_message(received)

    messages = asyncio.run(agent._build_llm_messages(received, [], reply, None))

    user_messages = [item for item in messages if item["role"] == "user"]
    assert user_messages == [{"role": "user", "content": "当前问题"}]
    assert all("旧问题" not in item["content"] for item in messages)


def test_context_capsule_is_system_only() -> None:
    agent = _Agent()
    received = AgentMessage(
        content="那数学呢",
        role="user",
        context={"context_capsule": "已完成背景：上一轮语文均分"},
    )
    reply = agent._init_reply_message(received)

    messages = asyncio.run(agent._build_llm_messages(received, [], reply, None))

    assert messages[-1] == {"role": "user", "content": "那数学呢"}
    assert messages[-2]["role"] == "system"
    assert "已完成背景" in messages[-2]["content"]
    assert len([item for item in messages if item["role"] == "user"]) == 1


def test_run_constraints_do_not_expose_sqlbot_history() -> None:
    constraints = _RunConstraints(
        locked_tables=[],
        required_keywords=[],
        resolved_question="只查当前问题",
        turn_type="follow_up",
        context_capsule="已完成背景",
    )

    raw = constraints.to_context()

    assert "conversation_history" not in raw
    assert raw["resolved_question"] == "只查当前问题"
