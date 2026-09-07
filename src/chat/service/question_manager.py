"""In-process lifecycle manager for same-request Human-in-the-Loop questions."""

from __future__ import annotations

import asyncio
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class QuestionNotFoundError(LookupError):
    pass


class QuestionForbiddenError(PermissionError):
    pass


class QuestionConflictError(RuntimeError):
    pass


class QuestionValidationError(ValueError):
    pass


@dataclass
class PendingQuestion:
    request_id: str
    conv_id: str
    user_id: int
    workspace_oid: int
    questions: list[dict[str, Any]]
    event: asyncio.Event
    loop: asyncio.AbstractEventLoop
    answers: list[list[str]] | None = None
    rejected: bool = False
    consumed: bool = False
    created_at: float = field(default_factory=time.monotonic)

    def to_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "conv_id": self.conv_id,
            "questions": self.questions,
        }


def validate_questions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 3:
        raise QuestionValidationError("questions must contain between 1 and 3 items")
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise QuestionValidationError("each question must be an object")
        question = str(item.get("question") or "").strip()
        header = str(item.get("header") or "").strip()
        multiple = bool(item.get("multiple", False))
        custom = bool(item.get("custom", True))
        if not question:
            raise QuestionValidationError("question text is required")
        if not header or len(header) > 30:
            raise QuestionValidationError("header is required and must not exceed 30 characters")
        raw_options = item.get("options") or []
        if not isinstance(raw_options, list):
            raise QuestionValidationError("options must be an array")
        options: list[dict[str, str]] = []
        labels: set[str] = set()
        for option in raw_options:
            if isinstance(option, str):
                label, description = option.strip(), ""
            elif isinstance(option, dict):
                label = str(option.get("label") or "").strip()
                description = str(option.get("description") or "").strip()
            else:
                raise QuestionValidationError("each option must be text or an object")
            if not label or label in labels:
                raise QuestionValidationError("option labels must be non-empty and unique")
            labels.add(label)
            normalized_option = {"label": label}
            if description:
                normalized_option["description"] = description
            options.append(normalized_option)
        if not options and not custom:
            raise QuestionValidationError("a question needs options or custom input")
        normalized.append(
            {
                "question": question,
                "header": header,
                "options": options,
                "multiple": multiple,
                "custom": custom,
            }
        )
    return normalized


def validate_answers(
    questions: list[dict[str, Any]],
    answers: Any,
) -> list[list[str]]:
    if not isinstance(answers, list) or len(answers) != len(questions):
        raise QuestionValidationError("answers length must match questions length")
    normalized: list[list[str]] = []
    for question, raw_answer in zip(questions, answers):
        if not isinstance(raw_answer, list):
            raise QuestionValidationError("each answer must be an array")
        values = [str(value).strip() for value in raw_answer if str(value).strip()]
        if not values:
            raise QuestionValidationError("every question requires an answer")
        if not question["multiple"] and len(values) > 1:
            raise QuestionValidationError("single-choice questions accept one answer")
        if any(len(value) > 500 for value in values):
            raise QuestionValidationError("answer must not exceed 500 characters")
        labels = {option["label"] for option in question["options"]}
        if not question["custom"] and any(value not in labels for value in values):
            raise QuestionValidationError("custom answers are disabled for this question")
        normalized.append(values)
    return normalized


class QuestionManager:
    """Thread-safe registry whose Events are awakened on their owning event loop."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingQuestion] = {}
        self._by_conversation: dict[str, str] = {}
        self._finished: dict[str, float] = {}
        self._lock = threading.RLock()

    def create(
        self,
        *,
        conv_id: str,
        user_id: int,
        workspace_oid: int,
        questions: list[dict[str, Any]],
    ) -> PendingQuestion:
        normalized = validate_questions(questions)
        loop = asyncio.get_running_loop()
        with self._lock:
            existing = self._by_conversation.get(conv_id)
            if existing and existing in self._pending:
                raise QuestionConflictError("conversation already has a pending question")
            request_id = f"que_{secrets.token_hex(8)}"
            pending = PendingQuestion(
                request_id=request_id,
                conv_id=conv_id,
                user_id=user_id,
                workspace_oid=workspace_oid,
                questions=normalized,
                event=asyncio.Event(),
                loop=loop,
            )
            self._pending[request_id] = pending
            self._by_conversation[conv_id] = request_id
            logger.info(
                "HITL pending created request_id=%s conversation_id=%s pending_count=%d",
                request_id,
                conv_id,
                len(self._pending),
            )
            return pending

    def get(self, request_id: str) -> PendingQuestion:
        with self._lock:
            pending = self._pending.get(request_id)
            if pending is not None:
                return pending
            if request_id in self._finished:
                raise QuestionConflictError("question has already been consumed")
            raise QuestionNotFoundError(request_id)

    def reply(
        self,
        request_id: str,
        *,
        user_id: int,
        workspace_oid: int,
        answers: Any,
    ) -> PendingQuestion:
        with self._lock:
            pending = self.get(request_id)
            self._assert_owner(pending, user_id, workspace_oid)
            if pending.consumed:
                raise QuestionConflictError("question has already been consumed")
            pending.answers = validate_answers(pending.questions, answers)
            pending.consumed = True
            self._finished[request_id] = time.monotonic()
            pending.loop.call_soon_threadsafe(pending.event.set)
            logger.info(
                "HITL question replied request_id=%s conversation_id=%s elapsed_ms=%d",
                request_id,
                pending.conv_id,
                int((time.monotonic() - pending.created_at) * 1000),
            )
            return pending

    def reject(
        self,
        request_id: str,
        *,
        user_id: int,
        workspace_oid: int,
    ) -> PendingQuestion:
        with self._lock:
            pending = self.get(request_id)
            self._assert_owner(pending, user_id, workspace_oid)
            if pending.consumed:
                raise QuestionConflictError("question has already been consumed")
            pending.rejected = True
            pending.consumed = True
            self._finished[request_id] = time.monotonic()
            pending.loop.call_soon_threadsafe(pending.event.set)
            logger.info(
                "HITL question rejected request_id=%s conversation_id=%s elapsed_ms=%d",
                request_id,
                pending.conv_id,
                int((time.monotonic() - pending.created_at) * 1000),
            )
            return pending

    def remove(self, request_id: str) -> None:
        with self._lock:
            pending = self._pending.pop(request_id, None)
            if pending and self._by_conversation.get(pending.conv_id) == request_id:
                self._by_conversation.pop(pending.conv_id, None)
            cutoff = time.monotonic() - 300
            self._finished = {
                key: when for key, when in self._finished.items() if when >= cutoff
            }

    def remove_for_conversation(self, conv_id: str) -> None:
        with self._lock:
            request_id = self._by_conversation.get(conv_id)
        if request_id:
            self.remove(request_id)

    def list_pending(self) -> list[PendingQuestion]:
        with self._lock:
            return list(self._pending.values())

    @staticmethod
    def _assert_owner(
        pending: PendingQuestion,
        user_id: int,
        workspace_oid: int,
    ) -> None:
        if pending.user_id != user_id or pending.workspace_oid != workspace_oid:
            raise QuestionForbiddenError("pending question does not belong to current scope")


_QUESTION_MANAGER = QuestionManager()


def get_question_manager() -> QuestionManager:
    return _QUESTION_MANAGER


__all__ = [
    "PendingQuestion",
    "QuestionConflictError",
    "QuestionForbiddenError",
    "QuestionManager",
    "QuestionNotFoundError",
    "QuestionValidationError",
    "get_question_manager",
    "validate_answers",
    "validate_questions",
]
