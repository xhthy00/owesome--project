"""ReActAgent：多轮 "thinking -> tool_call -> observation" 循环驱动的 Agent。

与 :class:`ConversableAgent` 的根本差异：

    ConversableAgent (基类)
        thinking -> review -> act -> verify -> 失败则 **重来同一轮**
        适合：单次对话生成 + 失败自修复

    ReActAgent (本类)
        第 N 轮:  thinking -> act(tool)
                  └─ terminate ? 结束 : observation 回灌 -> 进入第 N+1 轮
        适合：需要工具探查 / 多步推理 / 看结果再决定下一步

关键约定：
- LLM 每轮输出必须是 JSON `{"thoughts", "tool", "args"}`（由 ToolAction 解析）；
- **工具业务失败（如 SQL 报错）不触发重试，而是作为 observation 交给 LLM 下一轮
  自己修正**——这才是 ReAct 的精髓；
- 只有"工具不存在 / JSON 无法解析"这类框架错误才作为 observation 回灌并继续
  （LLM 下一轮应该会纠正格式）；
- ``terminate`` 工具的 ActionOutput.terminate=True 是唯一的正常退出信号。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agent.adapter.llm_adapter import _truncate_observation_for_llm
from src.agent.core.action.base import Action, ActionOutput
from src.agent.core.action.tool_action import ToolAction, build_repeat_tool_warning
from src.agent.core.agent import AgentMessage
from src.agent.core.base_agent import ConversableAgent
from src.agent.resource.tool.pack import ToolPack

logger = logging.getLogger(__name__)

#: 同一工具连续调用次数达该阈值后，在下一轮 observation 前**追加**一段软警告，
#: 推动 LLM 换工具或 terminate。不强制终止——max_rounds 已经是硬上限兜底。
#: 3 是经验值：list_tables → describe_table → sample_rows 这类合法同源探查
#: 一般不会超过 2 次；连续 3 次同工具几乎都是"坏循环"信号。
_REPEAT_TOOL_WARN_THRESHOLD = 3

#: 连续多少轮无法把 LLM 输出解析成工具调用后放弃整个循环。
#: 这类失败不像工具业务失败那样能带来新信息：模型每轮看到几乎相同的上下文，
#: 会稳定复现同一个格式错误，继续跑只是把 max_react_rounds 烧光再报同一条错。
_MAX_CONSECUTIVE_FORMAT_FAILURES = 3
_MAX_REPEATED_VENDOR_PROTOCOL_FAILURES = 2

#: 解析失败后注入下一轮 prompt 的强制纠偏指令。比 observation 回灌更硬——
#: observation 是"系统告诉我 Y"，容易被长 system prompt 淹没；fail_reason 直接
#: 拼在当轮 user 消息末尾，是模型最后读到的内容。
_FORMAT_REPAIR_HINT = (
    "你上一轮的输出无法被解析成工具调用。原因：{reason}\n"
    "从现在起**只**输出一个 JSON 对象，前后不要有任何解释、前言、Markdown 代码块，"
    "优先不要使用 `[TOOL_CALL]`、`<invoke>` 这类模型原生标记；"
    "若模型服务强制生成原生工具调用，则所有 XML 标签与参数必须完整闭合：\n"
    '{{"thoughts": "一句话说明理由", "tool": "工具名", "args": {{}}}}\n'
    "把 args 保持精简；已有信息足够时直接调用 `terminate`，结论写进 args.final_answer。"
)


class ReActAgent(ConversableAgent):
    """多轮 ReAct Agent 基类。

    子类通常只需定义 ``profile``（含带 ``{{tools_prompt}}`` 占位符的 desc），
    ``tool_pack`` 由构造参数注入。
    """

    max_react_rounds: int = 15
    _TOOL_CALL_SCHEMA: dict[str, Any] = {
        "type": "object",
        "required": ["tool", "args"],
        "properties": {
            "thoughts": {"type": "string"},
            "tool": {"type": "string"},
            "args": {"type": "object"},
        },
        "additionalProperties": True,
    }

    def __init__(
        self,
        *,
        tool_pack: ToolPack,
        actions: list[Action] | None = None,
        max_react_rounds: int | None = None,
        **kwargs: Any,
    ) -> None:
        if tool_pack is None:
            raise ValueError("ReActAgent requires a ToolPack")
        if actions is None:
            actions = [ToolAction(tool_pack=tool_pack)]
        super().__init__(actions=actions, **kwargs)
        self.tool_pack = tool_pack
        self._structured_output_warned = False
        if max_react_rounds is not None:
            self.max_react_rounds = max_react_rounds

    def _build_prompt_variables(self, reply: AgentMessage) -> dict[str, Any]:
        base = super()._build_prompt_variables(reply)
        base.setdefault("tools_prompt", self.tool_pack.render_prompt())
        return base

    async def thinking(self, messages: list[dict[str, str]], sender: Any) -> str:
        """优先请求结构化输出，失败时回退普通文本 chat。"""
        if self.llm_client is None:
            raise RuntimeError(f"{self.name}: llm_client is required for thinking()")
        chat_with_schema = getattr(self.llm_client, "chat_with_schema", None)
        if callable(chat_with_schema):
            try:
                schema = {
                    **self._TOOL_CALL_SCHEMA,
                    "properties": {
                        **self._TOOL_CALL_SCHEMA["properties"],
                        "tool": {
                            "type": "string",
                            "enum": self.tool_pack.names(),
                        },
                    },
                }
                obj = await chat_with_schema(messages, schema)
                if isinstance(obj, dict):
                    return json.dumps(obj, ensure_ascii=False)
            except Exception:
                # 曾经是 debug：结构化输出是防"格式抖动"的第一道闸门，静默降级会让
                # 它失效很久都没人发现。每个 agent 实例只告警一次，避免刷屏。
                if not self._structured_output_warned:
                    self._structured_output_warned = True
                    logger.warning(
                        "[%s] structured output unavailable, falling back to plain chat "
                        "— JSON 格式错误率会显著上升",
                        self.name,
                        exc_info=True,
                    )
        return await super().thinking(messages, sender)

    async def generate_reply(
        self,
        received_message: AgentMessage,
        sender: Any,
        reviewer: Any | None = None,
        rely_messages: list[AgentMessage] | None = None,
        **kwargs: Any,
    ) -> AgentMessage:
        import time

        reply = self._init_reply_message(received_message, rely_messages)
        running_rely: list[AgentMessage] = list(rely_messages or [])
        last_action_out: ActionOutput | None = None
        # E-guard：重复调用防护——仅追踪"成功解析到已知工具"的那个 tool_name，
        # 解析失败 / 未知工具会重置 streak（否则 LLM 稳定发错同一个错 name
        # 会被误报"重复调用"）。
        last_tool_name: str | None = None
        tool_streak: int = 0
        tool_call_cache: dict[str, ActionOutput] = {}
        preselected_tool_call = kwargs.pop("preselected_tool_call", None)
        if not (
            isinstance(preselected_tool_call, dict)
            and isinstance(preselected_tool_call.get("tool"), str)
            and isinstance(preselected_tool_call.get("args", {}), dict)
            and preselected_tool_call["tool"] in self.tool_pack
        ):
            preselected_tool_call = None
        # 格式失败（JSON 解析不出 / 缺 tool / 未知工具）单独计数：它与工具业务失败
        # 不同，重跑不会带来新信息，必须靠 fail_reason 纠偏并在连续失败时尽早退出。
        format_failures: int = 0
        format_fail_reason: str | None = None
        gave_up_on_format = False
        repeated_vendor_failure = False

        for round_idx in range(self.max_react_rounds):
            reply.rounds = round_idx + 1

            messages = await self._build_llm_messages(
                received_message=received_message,
                rely_messages=running_rely,
                reply=reply,
                fail_reason=format_fail_reason,
            )
            if round_idx == 0 and preselected_tool_call is not None:
                llm_text = json.dumps(preselected_tool_call, ensure_ascii=False)
            else:
                llm_text = await self.thinking(messages, sender)
            reply.content = llm_text

            await self._emit(
                "agent_thought",
                {"round": reply.rounds, "agent": self.name, "text": llm_text},
            )

            t0 = time.time()
            action_out = await self.act(
                reply,
                sender=sender,
                reviewer=reviewer,
                round_idx=reply.rounds,
                agent_name=self.name,
                tool_call_cache=tool_call_cache,
                **kwargs,
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            if round_idx == 0 and preselected_tool_call is not None:
                tool_data = (action_out.extra or {}).get("tool_data")
                if isinstance(tool_data, dict) and tool_data.get("error"):
                    action_out = ActionOutput(
                        is_exe_success=False,
                        content=action_out.content,
                        action=action_out.action,
                        thoughts=action_out.thoughts,
                        observations=action_out.observations,
                        have_retry=False,
                        extra={
                            **dict(action_out.extra or {}),
                            "failure_code": "missing_business_input",
                        },
                    )
            reply.action_report = action_out
            last_action_out = action_out

            await self._emit_tool_events(reply.rounds, action_out, elapsed_ms)

            if action_out.terminate:
                if action_out.content:
                    reply.content = action_out.content
                await self._emit(
                    "final_answer",
                    {"agent": self.name, "text": reply.content or ""},
                )
                await self.write_memories(received_message, reply, action_out)
                return reply

            # ToolAction 把所有"没解析出一个可执行工具"的情况都标成 action="tool_call"。
            failure_code = str((action_out.extra or {}).get("failure_code") or "")
            is_format_failure = not action_out.is_exe_success and (
                failure_code
                in {"parse_error", "truncated_output", "unknown_tool", "argument_error"}
                or (not failure_code and action_out.action == ToolAction.name)
            )
            if is_format_failure:
                format_failures += 1
                format_fail_reason = _FORMAT_REPAIR_HINT.format(
                    reason=(action_out.content or "输出不是合法的工具调用 JSON").strip()
                )
                logger.warning(
                    "[%s] format failure %d/%d at round %d: %s",
                    self.name,
                    format_failures,
                    _MAX_CONSECUTIVE_FORMAT_FAILURES,
                    reply.rounds,
                    action_out.content,
                )
            else:
                format_failures = 0
                format_fail_reason = None

            # 统计 streak：仅"成功 + 已知工具 + 非 terminate"的轮计入。
            current_tool = (
                action_out.action
                if action_out.is_exe_success and action_out.action
                and action_out.action != "tool_call"
                else None
            )
            if current_tool:
                if current_tool == last_tool_name:
                    tool_streak += 1
                else:
                    last_tool_name = current_tool
                    tool_streak = 1
            else:
                last_tool_name = None
                tool_streak = 0

            streak_warning: str | None = None
            if tool_streak >= _REPEAT_TOOL_WARN_THRESHOLD and last_tool_name:
                streak_warning = build_repeat_tool_warning(last_tool_name, tool_streak)
                logger.warning(
                    "[%s] tool streak=%d for %r at round %d — injecting soft warning",
                    self.name, tool_streak, last_tool_name, reply.rounds,
                )

            running_rely.extend(
                self._format_trace(
                    thought_text=llm_text,
                    action_out=action_out,
                    streak_warning=streak_warning,
                )
            )

            if format_failures >= _MAX_CONSECUTIVE_FORMAT_FAILURES:
                gave_up_on_format = True
                logger.error(
                    "[%s] giving up after %d consecutive format failures at round %d",
                    self.name,
                    format_failures,
                    reply.rounds,
                )
                break
            if (
                format_failures >= _MAX_REPEATED_VENDOR_PROTOCOL_FAILURES
                and (action_out.extra or {}).get("protocol") == "minimax_xml"
            ):
                gave_up_on_format = True
                repeated_vendor_failure = True
                logger.error(
                    "[%s] repeated invalid MiniMax XML protocol at round %d",
                    self.name,
                    reply.rounds,
                )
                break

            if not action_out.have_retry:
                logger.info(
                    "[%s] action declared have_retry=False at round %d, stopping loop",
                    self.name,
                    reply.rounds,
                )
                break

        if last_action_out is None:
            reply.action_report = ActionOutput(
                is_exe_success=False,
                content="ReAct loop produced no action",
                have_retry=False,
            )
        elif last_action_out.is_exe_success and (
            (last_action_out.observations and str(last_action_out.observations).strip())
            or (last_action_out.content and str(last_action_out.content).strip())
        ):
            # 兜底收敛：达到轮数上限但最后一次工具结果有效时，自动收敛成最终答复，
            # 避免前端把这类“已拿到结果但忘了 terminate”的场景误判为失败。
            final_text = str(last_action_out.observations or last_action_out.content or "").strip()
            reply.content = final_text
            reply.action_report = ActionOutput(
                is_exe_success=True,
                content=final_text,
                thoughts=last_action_out.thoughts,
                action=last_action_out.action,
                observations=last_action_out.observations,
                terminate=True,
                have_retry=False,
                extra=dict(last_action_out.extra or {}),
            )
            await self._emit(
                "final_answer",
                {"agent": self.name, "text": reply.content or ""},
            )
        else:
            if gave_up_on_format:
                failure_code = str((last_action_out.extra or {}).get("failure_code") or "")
                if repeated_vendor_failure:
                    headline = "模型连续返回无法完整解析的 MiniMax XML 工具调用，已停止重复重试。"
                elif failure_code == "truncated_output":
                    headline = "模型连续返回结构不完整的工具调用，疑似响应被截断，已提前终止。"
                elif failure_code == "unknown_tool":
                    headline = "模型连续选择不可用工具，已提前终止。"
                elif failure_code == "argument_error":
                    headline = "模型连续生成不匹配的工具参数，已提前终止。"
                else:
                    headline = (
                        f"连续 {_MAX_CONSECUTIVE_FORMAT_FAILURES} 轮无法解析模型工具协议，"
                        f"已提前终止（未耗尽 {self.max_react_rounds} 轮）。"
                    )
            else:
                headline = f"达到最大 ReAct 轮数 ({self.max_react_rounds}) 仍未调用 terminate。"
            reply.action_report = ActionOutput(
                is_exe_success=False,
                content=(
                    f"{headline}"
                    f" 最后一次观察：{last_action_out.observations or last_action_out.content}"
                ),
                thoughts=last_action_out.thoughts,
                action=last_action_out.action,
                observations=last_action_out.observations,
                have_retry=False,
            )
        await self.write_memories(received_message, reply, reply.action_report)
        return reply

    async def _emit_tool_events(
        self,
        round_idx: int,
        action_out: ActionOutput,
        elapsed_ms: int,
    ) -> None:
        """把一次 act 拆成 tool_call + tool_result 两条 SSE 事件。

        约定：
        - 成功：action_out.action 是 tool_name，extra['tool_args'] 是解析后的参数；
        - 失败（JSON 解析 / 未知工具 / 参数不匹配）：action_out.action 为 "tool_call"
          字面量，此时不发 tool_call 而只发 tool_result 记录失败原因，保持信号清晰。
        """
        tool_name = action_out.action
        is_known_tool = bool(action_out.is_exe_success) and tool_name and tool_name != "tool_call"
        is_terminate = bool(action_out.terminate)
        is_deduplicated = bool((action_out.extra or {}).get("deduplicated"))

        if is_known_tool and not is_terminate and not is_deduplicated:
            await self._emit(
                "tool_call",
                {
                    "round": round_idx,
                    "agent": self.name,
                    "tool": tool_name,
                    "args": dict(action_out.extra.get("tool_args") or {}),
                    "thought": action_out.thoughts or "",
                },
            )

        await self._emit(
            "tool_result",
            {
                "round": round_idx,
                "agent": self.name,
                "tool": tool_name or "tool_call",
                "success": bool(action_out.is_exe_success),
                "content": action_out.observations or action_out.content or "",
                # 去重命中时禁止再带 HTML，避免前端重复挂载报告
                "data": None if is_deduplicated else action_out.extra.get("tool_data"),
                "elapsed_ms": elapsed_ms,
                "terminate": bool(action_out.terminate),
                "deduplicated": is_deduplicated,
            },
        )

    def _format_trace(
        self,
        thought_text: str,
        action_out: ActionOutput,
        streak_warning: str | None = None,
    ) -> list[AgentMessage]:
        """把一轮 (thought, observation) 变成两条 AgentMessage 塞回 rely_messages。

        使用 user 角色表达 observation 是刻意为之：下一轮 LLM 看到"我上次说了 X，
        系统告诉我 Y"，自然会把 Y 当作新输入推进；若用 assistant 角色，会被
        ChatCompletion 视为"LLM 之前也这么说"，容易陷入 parroting。

        Args:
            streak_warning: 非 None 时会**追加**在 observation 前，作为软警告
                推动 LLM 跳出重复调用。注意**不污染** SSE tool_result payload——
                那里保留原始工具返回，前端需要干净信号；警告只进 ReAct 上下文。
        """
        marker = "✓" if action_out.is_exe_success else "✗"
        tool_name = action_out.action or "tool"
        observation = action_out.observations or action_out.content or "(no observation)"
        observation = _truncate_observation_for_llm(str(observation))
        observation_block = f"[{marker} observation from {tool_name}]\n{observation}"
        if streak_warning:
            observation_block = f"{streak_warning}\n\n{observation_block}"

        return [
            AgentMessage(
                role="assistant",
                content=thought_text,
                sender=self.name,
            ),
            AgentMessage(
                role="user",
                content=observation_block,
                sender="tool",
            ),
        ]
