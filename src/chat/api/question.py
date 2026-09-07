"""Reply and reject endpoints for same-request Agentic questions."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from audit.service.decorators import audit_access
from chat.crud import chat as chat_crud
from chat.schemas import QuestionReplyRequest
from common.core.database import get_session
from common.schemas.response import success_response
from src.chat.service.question_manager import (
    QuestionConflictError,
    QuestionForbiddenError,
    QuestionNotFoundError,
    QuestionValidationError,
    get_question_manager,
)
from system.api.auth_deps import get_current_user
from system.schemas import UserResponse
from system.workspace_scope import get_workspace_oid

router = APIRouter(prefix="/chat/question", tags=["chat"])


def _pending_or_http_error(request_id: str):
    try:
        return get_question_manager().get(request_id)
    except QuestionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Pending question not found") from exc
    except QuestionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _assert_conversation_owner(
    pending,
    *,
    session: Session,
    current_user: UserResponse,
    workspace_oid: int,
) -> None:
    if pending.user_id != current_user.id or pending.workspace_oid != workspace_oid:
        raise HTTPException(status_code=403, detail="Pending question is not in current scope")
    if pending.conv_id == "0":
        return
    try:
        conversation_id = int(pending.conv_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid conversation scope") from exc
    conversation = chat_crud.get_conversation_by_id(
        session,
        conversation_id,
        current_user.id,
        workspace_oid,
    )
    if conversation is None:
        raise HTTPException(status_code=403, detail="Conversation is not in current scope")


@router.post("/{request_id}/reply", summary="Reply to an Agentic question")
@audit_access()
async def reply_question(
    request_id: str,
    body: QuestionReplyRequest,
    http_request: Request,
    session: Session = Depends(get_session),
    current_user: UserResponse = Depends(get_current_user),
    workspace_oid: int = Depends(get_workspace_oid),
):
    pending = _pending_or_http_error(request_id)
    _assert_conversation_owner(
        pending,
        session=session,
        current_user=current_user,
        workspace_oid=workspace_oid,
    )
    try:
        get_question_manager().reply(
            request_id,
            user_id=current_user.id,
            workspace_oid=workspace_oid,
            answers=body.answers,
        )
    except QuestionForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except QuestionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QuestionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success_response(data={"request_id": request_id})


@router.post("/{request_id}/reject", summary="Reject an Agentic question")
@audit_access()
async def reject_question(
    request_id: str,
    http_request: Request,
    session: Session = Depends(get_session),
    current_user: UserResponse = Depends(get_current_user),
    workspace_oid: int = Depends(get_workspace_oid),
):
    pending = _pending_or_http_error(request_id)
    _assert_conversation_owner(
        pending,
        session=session,
        current_user=current_user,
        workspace_oid=workspace_oid,
    )
    try:
        get_question_manager().reject(
            request_id,
            user_id=current_user.id,
            workspace_oid=workspace_oid,
        )
    except QuestionForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except QuestionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return success_response(data={"request_id": request_id})


__all__ = ["router"]
