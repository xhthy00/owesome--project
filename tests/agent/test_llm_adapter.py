"""LangChainLlmClient 适配器测试。

不依赖真实 LLM：构造一个最小 FakeChatModel，验证：
- dict 消息正确转为 LangChain BaseMessage（含 system/user/assistant 三角色）；
- 优先走 ``ainvoke`` 异步路径；
- 有 ``_llm`` 属性的 wrapper 能自动拆出内层模型；
- 无 ``ainvoke`` 时降级到 ``invoke`` via ``asyncio.to_thread``。
"""

from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.agent.adapter.llm_adapter import (
    LangChainLlmClient,
    _dict_messages_to_langchain,
)


class FakeChatModel:
    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.ainvoke_calls: list[list[BaseMessage]] = []

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.ainvoke_calls.append(list(messages))
        return AIMessage(content=self.reply)


class FakeSyncOnlyModel:
    def __init__(self, reply: str = "sync-ok") -> None:
        self.reply = reply
        self.invoke_calls: list[list[BaseMessage]] = []

    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.invoke_calls.append(list(messages))
        return AIMessage(content=self.reply)


class FakeWrapper:
    """模拟 OpenAILLM / OllamaLLM：真正的聊天模型挂在 ``_llm`` 上。"""

    def __init__(self, chat_model) -> None:
        self._llm = chat_model


def _run(coro):
    return asyncio.run(coro)


def test_dict_messages_conversion_roles():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "unknown", "content": "default-to-user"},
    ]
    lc = _dict_messages_to_langchain(msgs)

    assert isinstance(lc[0], SystemMessage) and lc[0].content == "sys"
    assert isinstance(lc[1], HumanMessage) and lc[1].content == "u1"
    assert isinstance(lc[2], AIMessage) and lc[2].content == "a1"
    assert isinstance(lc[3], HumanMessage)


def test_adapter_uses_ainvoke_when_available():
    model = FakeChatModel(reply="hello from async")
    client = LangChainLlmClient(llm=model)

    out = _run(client.chat([{"role": "user", "content": "hi"}]))

    assert out == "hello from async"
    assert len(model.ainvoke_calls) == 1
    assert isinstance(model.ainvoke_calls[0][0], HumanMessage)


def test_adapter_unwraps_wrapper_with_underscore_llm():
    model = FakeChatModel(reply="unwrapped")
    wrapper = FakeWrapper(chat_model=model)
    client = LangChainLlmClient(llm=wrapper)

    out = _run(client.chat([{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]))

    assert out == "unwrapped"
    assert len(model.ainvoke_calls) == 1
    converted = model.ainvoke_calls[0]
    assert isinstance(converted[0], SystemMessage)
    assert isinstance(converted[1], HumanMessage)


def test_adapter_falls_back_to_sync_invoke_via_thread():
    model = FakeSyncOnlyModel(reply="sync path")
    client = LangChainLlmClient(llm=model)

    out = _run(client.chat([{"role": "user", "content": "hi"}]))

    assert out == "sync path"
    assert len(model.invoke_calls) == 1


def test_adapter_handles_list_content_response():
    class ListContentModel:
        async def ainvoke(self, messages):
            return AIMessage(content=["part-a", "part-b"])

    client = LangChainLlmClient(llm=ListContentModel())
    out = _run(client.chat([{"role": "user", "content": "x"}]))
    assert "part-a" in out and "part-b" in out


def test_adapter_lazy_loads_default_llm(monkeypatch):
    model = FakeChatModel(reply="from-default")

    def fake_get_default_llm():
        return FakeWrapper(chat_model=model)

    import src.llm.service as llm_service

    monkeypatch.setattr(llm_service, "get_default_llm", fake_get_default_llm)

    client = LangChainLlmClient()
    out = _run(client.chat([{"role": "user", "content": "hi"}]))

    assert out == "from-default"
