"""ConversableAgent：可对话 Agent 的核心实现。

主循环分五段（对齐 DB-GPT 设计）：

    thinking  -> LLM 推理，产出原始文本
    review    -> 自检 / 审查员检查，决定是否直接重来
    act       -> 交给 Action 执行，产出结构化 ActionOutput
    verify    -> 核对执行结果是否真的达成目标
    self-optimization -> 记忆 / 失败原因回填，进入下一轮重试

任何一步失败都允许最多 ``max_retry_count`` 次重试；失败原因会回灌到下一
轮的 prompt，让模型"看得到自己上次错在哪里"。

子类通常只需要：
- 定义 class-level ``profile`` 与 ``actions``；
- 重写 ``_build_prompt_variables`` / ``correctness_check`` 等 hook。
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Protocol

from src.agent.core.action.base import Action, ActionOutput
from src.agent.core.agent import AgentMessage, AgentReviewInfo
from src.agent.core.memory.agent_memory import AgentMemory
from src.agent.core.profile import ProfileConfig

logger = logging.getLogger(__name__)


class LlmClient(Protocol):
    """最小 LLM 客户端协议。真实实现由 ``src.llm.service`` 提供，测试用 Fake。"""

    async def chat(self, messages: list[dict[str, str]]) -> str:  # pragma: no cover - 协议声明
        ...


StreamCallback = Callable[[str, dict[str, Any]], Awaitable[None]]
"""可选的流式/事件回调：(event_type, payload) -> None。"""


class ConversableAgent:
    profile: ProfileConfig
    actions: list[Action] = []
    max_retry_count: int = 3

    def __init__(
        self,
        *,
        llm_client: LlmClient | None = None,
        memory: AgentMemory | None = None,
        actions: list[Action] | None = None,
        profile: ProfileConfig | None = None,
        max_retry_count: int | None = None,
        stream_callback: StreamCallback | None = None,
    ) -> None:
        if profile is not None:
            self.profile = profile
        if not getattr(self, "profile", None):
            raise ValueError(
                f"{type(self).__name__} must define a class-level ``profile`` "
                f"or pass ``profile=`` at init."
            )
        self.llm_client = llm_client
        self.memory = memory
        self.actions = list(actions) if actions is not None else list(type(self).actions or [])
        if max_retry_count is not None:
            self.max_retry_count = max_retry_count
        self.stream_callback = stream_callback

    async def _emit(self, event: str, payload: dict[str, Any]) -> None:
        """发一条流式事件（仅在配置了 stream_callback 时生效）。

        约定 payload 只含 JSON 可序列化数据；调用方不应期待事件一定被消费。
        内部异常会被吞掉并打日志——流式回调绝不能拖垮主循环。
        """
        cb = self.stream_callback
        if cb is None:
            return
        try:
            await cb(event, payload)
        except Exception:  # noqa: BLE001 - 流回调隔离
            logger.exception("[%s] stream_callback raised on event %s", self.name, event)

    @property
    def name(self) -> str:
        return self.profile.name

    @property
    def role(self) -> str:
        return self.profile.role

    async def generate_reply(
        self,
        received_message: AgentMessage,
        sender: Any,
        reviewer: Any | None = None,
        rely_messages: list[AgentMessage] | None = None,
        **kwargs: Any,
    ) -> AgentMessage:
        """主循环入口：返回一条最终回复消息。"""
        reply = self._init_reply_message(received_message, rely_messages)
        fail_reason: str | None = None
        last_action_out: ActionOutput | None = None

        for attempt in range(self.max_retry_count):
            reply.rounds = attempt + 1

            messages = await self._build_llm_messages(
                received_message=received_message,
                rely_messages=rely_messages or [],
                reply=reply,
                fail_reason=fail_reason,
            )
            llm_text = await self.thinking(messages, sender)
            reply.content = llm_text

            approve, comments = await self.review(llm_text, reviewer or self)
            reply.review_info = AgentReviewInfo(approve=approve, comments=comments)
            if not approve:
                fail_reason = comments or "review rejected"
                logger.info("[%s] review rejected (round=%d): %s", self.name, attempt + 1, fail_reason)
                continue

            action_out = await self.act(reply, sender=sender, reviewer=reviewer, **kwargs)
            reply.action_report = action_out
            last_action_out = action_out

            ok, reason = await self.verify(reply, sender=sender, reviewer=reviewer)
            if ok:
                await self.write_memories(received_message, reply, action_out)
                return reply

            fail_reason = reason or action_out.content or "verify failed"
            logger.info("[%s] verify failed (round=%d): %s", self.name, attempt + 1, fail_reason)

            if not action_out.have_retry:
                break

        if reply.action_report is None:
            reply.action_report = ActionOutput(
                is_exe_success=False,
                content=fail_reason or "max retry reached without action",
                have_retry=False,
            )
        else:
            reply.action_report = last_action_out or reply.action_report
            reply.action_report.is_exe_success = False
            if fail_reason:
                reply.action_report.content = fail_reason

        await self.write_memories(received_message, reply, reply.action_report)
        return reply

    def _init_reply_message(
        self,
        received_message: AgentMessage,
        rely_messages: list[AgentMessage] | None = None,
    ) -> AgentMessage:
        return AgentMessage(
            content=None,
            current_goal=received_message.current_goal or received_message.content,
            role="assistant",
            sender=self.name,
            context=dict(received_message.context or {}),
        )

    async def _build_llm_messages(
        self,
        received_message: AgentMessage,
        rely_messages: list[AgentMessage],
        reply: AgentMessage,
        fail_reason: str | None,
    ) -> list[dict[str, str]]:
        system = self.profile.render_system_prompt(self._build_prompt_variables(reply))
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]

        for m in rely_messages:
            if m.content:
                messages.append({"role": m.role or "user", "content": m.content})

        user_content = received_message.content or ""
        if fail_reason:
            user_content = (
                f"{user_content}\n\n"
                f"[上一轮失败原因]\n{fail_reason}\n"
                f"请基于以上反馈修正后重新作答。"
            )
        messages.append({"role": "user", "content": user_content})
        return messages

    def _build_prompt_variables(self, reply: AgentMessage) -> dict[str, Any]:
        """子类可覆盖，向 system prompt 注入运行时变量。"""
        return dict(reply.context or {})

    async def thinking(self, messages: list[dict[str, str]], sender: Any) -> str:
        if self.llm_client is None:
            raise RuntimeError(f"{self.name}: llm_client is required for thinking()")
        return await self.llm_client.chat(messages)

    async def review(self, content: str, reviewer: Any) -> tuple[bool, str | None]:
        """默认放行。子类/审查员可重写。"""
        return True, None

    async def act(
        self,
        message: AgentMessage,
        sender: Any,
        reviewer: Any | None = None,
        **kwargs: Any,
    ) -> ActionOutput:
        """默认行为：把 thinking 的原文直接作为 ActionOutput（适合无 Action 的对话型 Agent）；
        若配置了 actions，则走第一个 Action。"""
        if not self.actions:
            return ActionOutput(content=message.content or "", is_exe_success=True)

        action = self.actions[0]
        return await action.run(
            ai_message=message.content or "",
            sender=sender,
            reviewer=reviewer,
            memory=self.memory,
            **kwargs,
        )

    async def verify(
        self,
        message: AgentMessage,
        sender: Any,
        reviewer: Any | None = None,
    ) -> tuple[bool, str | None]:
        out = message.action_report
        if out is None:
            return False, "no action output"
        if not out.is_exe_success:
            return False, out.content or "action failed"
        return await self.correctness_check(message)

    async def correctness_check(self, message: AgentMessage) -> tuple[bool, str | None]:
        """领域层正确性校验，默认通过。子类按需重写。"""
        return True, None

    async def write_memories(
        self,
        question: AgentMessage,
        reply: AgentMessage,
        action_output: ActionOutput | None,
    ) -> None:
        if self.memory is None:
            return
        await self.memory.write(
            {
                "agent": self.name,
                "question": question.content,
                "answer": reply.content,
                "action": action_output.action if action_output else None,
                "observations": action_output.observations if action_output else None,
                "is_success": bool(action_output and action_output.is_exe_success),
            }
        )
