"""意图识别 Action：空槽即向用户提问。

移植自 DB-GPT ``IntentRecognitionAction.run()``——遍历意图定义里的槽位，
只要有一个取不到值，就产出 ``is_exe_success=False`` + ``ask_user=True`` 的
ActionOutput，把控制权交回用户，而不是让下游 Agent 去猜。
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from src.agent.core.action.base import Action, ActionOutput
from src.agent.education.intent_detect import EduIntent, parse_intent_payload


class IntentRecognitionAction(Action):
    """把 ``EduIntent`` 转成 ActionOutput：缺槽 → ask_user，齐活 → 放行。"""

    name = "intent_recognition"

    async def run(self, ai_message: str, **kwargs: Any) -> ActionOutput:
        try:
            intent = parse_intent_payload(ai_message)
        except Exception as exc:  # noqa: BLE001
            return ActionOutput(
                is_exe_success=False,
                content=f"intent parse failed: {exc}",
                view="意图识别失败，请换个说法重试。",
            )
        return build_intent_action_output(
            intent,
            missing=kwargs.get("missing"),
            prompt=kwargs.get("prompt"),
            payload=kwargs.get("payload"),
        )


def build_intent_action_output(
    intent: EduIntent | None,
    *,
    missing: list[str] | None = None,
    prompt: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> ActionOutput:
    """按空槽循环产出 ActionOutput。

    ``missing`` 由规则层（``candidate_missing_slots`` + 报告必填矩阵）给出，
    与 DB-GPT 遍历 ``intent.slots`` 找空值是同一件事——只是我们的必填集合按
    报告类型收窄了，不是"所有声明的槽都必须有值"。

    Args:
        intent: LLM 意图结果，可能为空（LLM 不可用时走纯规则）。
        missing: 仍然缺失的槽位。非空即触发 ask_user。
        prompt: 追问文案；缺省用 ``intent.ask_user``。
        payload: 落库/回放用的 pending 快照，写进 ``content``。
    """
    empty_slots = [s for s in (missing or []) if s]
    ask = (prompt or "").strip() or (intent.ask_user if intent else "") or ""
    body = dict(payload or {})
    if intent is not None and intent.ok and "intent" not in body:
        body["intent"] = intent.to_dict()

    if not empty_slots:
        return ActionOutput(
            content=json.dumps(body, ensure_ascii=False) if body else "",
            is_exe_success=True,
            view=intent.user_input if intent else "",
        )

    return ActionOutput(
        content=json.dumps(body, ensure_ascii=False),
        is_exe_success=False,
        view=ask,
        # 缺的是用户才知道的信息，重试再多轮也变不出来——必须问。
        have_retry=False,
        ask_user=True,
        extra={"missing_slots": empty_slots},
    )


__all__ = ["IntentRecognitionAction", "build_intent_action_output"]
