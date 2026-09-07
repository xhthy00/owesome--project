"""Request-bound Agentic question tool."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from src.agent.resource.tool.base import ToolParameter
from src.agent.resource.tool.function_tool import FunctionTool
from src.chat.service.agent_runner import EmitCallback
from src.chat.service.question_manager import QuestionManager, validate_questions

logger = logging.getLogger(__name__)


def _parse_questions(value: Any) -> list[dict[str, Any]]:
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("questions must be valid JSON") from exc
    if isinstance(parsed, dict):
        parsed = parsed.get("questions")
    return validate_questions(parsed)


def _format_answers(
    questions: list[dict[str, Any]],
    answers: list[list[str]],
) -> str:
    lines = ["The user answered the clarification questions:"]
    for question, values in zip(questions, answers):
        lines.append(f"- {question['header']}: {', '.join(values)}")
    return "\n".join(lines)


def make_question(
    *,
    emit: EmitCallback,
    question_manager: QuestionManager,
    conversation_id: int | None,
    user_id: int,
    workspace_oid: int,
    timeout_seconds: float = 300,
) -> FunctionTool:
    """Create a question tool bound to one active chat request."""

    async def question(questions: str) -> str:
        """Ask the user one to three structured questions and wait for answers."""
        parsed = _parse_questions(questions)
        pending = question_manager.create(
            conv_id=str(conversation_id or 0),
            user_id=user_id,
            workspace_oid=workspace_oid,
            questions=parsed,
        )
        await emit("question.asked", pending.to_payload())
        logger.info(
            "HITL question asked request_id=%s conversation_id=%s headers=%s",
            pending.request_id,
            pending.conv_id,
            [item["header"] for item in parsed],
        )
        timed_out = False
        try:
            await asyncio.wait_for(pending.event.wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            timed_out = True
            logger.info(
                "HITL question timed out request_id=%s conversation_id=%s timeout_seconds=%s",
                pending.request_id,
                pending.conv_id,
                timeout_seconds,
            )
            await emit(
                "question.rejected",
                {"request_id": pending.request_id, "conv_id": pending.conv_id},
            )
        finally:
            answers = pending.answers
            rejected = pending.rejected
            question_manager.remove(pending.request_id)

        if timed_out:
            return (
                f"Question timed out after {int(timeout_seconds)} seconds. "
                "Proceeding without user answer."
            )
        if rejected:
            return "The user dismissed the question. Proceeding without answer."
        return _format_answers(parsed, answers or [])

    return FunctionTool(
        fn=question,
        name="question",
        description=(
            "当存在多个同样合理且无法从数据、权限或上下文推断的分析方向时，"
            "向用户提出结构化选择并等待回答。不要用于查询数据库可获得的信息。"
        ),
        parameters=[
            ToolParameter(
                name="questions",
                type="string",
                description=(
                    "JSON 数组；每项含 question/header/options，"
                    "可选 multiple/custom，最多三项"
                ),
                required=True,
            )
        ],
    )


__all__ = ["make_question"]
