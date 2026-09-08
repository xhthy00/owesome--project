import asyncio
from types import SimpleNamespace

from src.chat.service import conversation_context as context


def test_context_filters_failed_and_pending_turns() -> None:
    records = [
        SimpleNamespace(
            id=1,
            question="高三(1)班期中数学成绩",
            resolved_question=None,
            context_summary="已生成数学成绩概览",
            summary="<html>long report</html>",
            sql_answer=None,
            reasoning=None,
            exec_result=None,
            is_success=True,
        ),
        SimpleNamespace(
            id=2,
            question="失败问题",
            resolved_question=None,
            context_summary="不应出现",
            summary=None,
            sql_answer=None,
            reasoning=None,
            exec_result=None,
            is_success=False,
        ),
    ]

    result = context.context_from_records(records)

    assert result.latest_record_id == 1
    assert "数学成绩概览" in result.brief
    assert "不应出现" not in result.brief
    assert "<html>" not in result.brief


def test_merge_inherited_slots_honors_reset() -> None:
    inherited = {"exam_name": "期中考试", "class_name": "高三(1)班"}

    result = context.merge_inherited_slots({}, inherited, "换个考试，再看数学")

    assert "exam_name" not in result
    assert result["class_name"] == "高三(1)班"


def test_standalone_question_does_not_load_history(monkeypatch) -> None:
    def fail_if_loaded(*args, **kwargs):
        raise AssertionError("完整新问题不应加载历史")

    monkeypatch.setattr(context, "load_turn_context", fail_if_loaded)
    result = asyncio.run(
        context.resolve_turn_context(
            question="查询扬州中学高三(2)班期末数学平均分",
            conversation_id=10,
            user_id=1,
        )
    )

    assert result.turn_type == context.TURN_STANDALONE
    assert result.resolved_question == "查询扬州中学高三(2)班期末数学平均分"
    assert not result.context_capsule


def test_follow_up_is_rewritten_to_one_current_task(monkeypatch) -> None:
    monkeypatch.setattr(
        context,
        "load_turn_context",
        lambda *args, **kwargs: context.TurnContext(
            inherited={"exam_name": "期中考试", "class_name": "高三(1)班"},
            brief="用户：查询高三(1)班期中语文均分\n助手：均分为 110 分",
            latest_record_id=7,
        ),
    )

    result = asyncio.run(
        context.resolve_turn_context(
            question="那数学呢",
            conversation_id=10,
            user_id=1,
        )
    )

    assert result.turn_type == context.TURN_FOLLOW_UP
    assert result.parent_record_id == 7
    assert result.resolved_question.startswith("那数学呢")
    assert "考试=期中考试" in result.resolved_question
    assert "班级=高三(1)班" in result.resolved_question
    assert not result.context_capsule


def test_short_question_without_history_is_standalone(monkeypatch) -> None:
    monkeypatch.setattr(context, "load_turn_context", lambda *args, **kwargs: context.TurnContext())

    result = asyncio.run(
        context.resolve_turn_context(
            question="有多少用户",
            conversation_id=None,
            user_id=1,
        )
    )

    assert result.turn_type == context.TURN_STANDALONE


def test_retry_never_loads_session_history(monkeypatch) -> None:
    def fail_if_loaded(*args, **kwargs):
        raise AssertionError("retry 不得加载会话级历史")

    monkeypatch.setattr(context, "load_turn_context", fail_if_loaded)
    result = asyncio.run(
        context.resolve_turn_context(
            question="期中考试",
            conversation_id=10,
            user_id=1,
            is_retry_chat=True,
            parent_record_id=9,
        )
    )

    assert result.turn_type == context.TURN_RETRY
    assert result.parent_record_id == 9
    assert not result.context_capsule
