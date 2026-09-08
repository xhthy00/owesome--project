import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

from src.chat.schemas import ChatRequest
from src.chat.service.agent_runner import _begin_or_resume_agent_run


def test_waiting_resume_loads_only_current_run_messages(monkeypatch) -> None:
    waiting = SimpleNamespace(
        id=12,
        agent_mode="agent",
        datasource_id=3,
        record_id=8,
        last_speaker="Intent",
        message_round=2,
        retry_count=0,
        state="waiting",
    )
    calls = {"listed": 0, "created": 0}

    @contextmanager
    def fake_session():
        yield object()

    def fake_update(session, run, **values):
        for key, value in values.items():
            if key != "clear_pending" and value is not None:
                setattr(run, key, value)
        return run

    def fake_list(session, run_id):
        calls["listed"] += 1
        assert run_id == 12
        return [
            SimpleNamespace(
                round=1,
                sender="user",
                receiver="Intent",
                role="user",
                content="生成班级报告",
                action_report=None,
                context=None,
            ),
            SimpleNamespace(
                round=2,
                sender="Intent",
                receiver="user",
                role="assistant",
                content="请补充考试",
                action_report={"ask_user": True},
                context={"pending": True},
            ),
        ]

    monkeypatch.setattr("src.common.core.database.get_db_session", fake_session)
    monkeypatch.setattr(
        "src.chat.crud.agent_run.get_waiting_agent_run",
        lambda *args, **kwargs: waiting,
    )
    monkeypatch.setattr("src.chat.crud.agent_run.update_agent_run", fake_update)
    monkeypatch.setattr("src.chat.crud.agent_run.append_agent_message", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.chat.crud.agent_run.list_agent_messages", fake_list)

    def fail_create(*args, **kwargs):
        calls["created"] += 1
        raise AssertionError("WAITING 恢复不得创建新 run")

    monkeypatch.setattr("src.chat.crud.agent_run.create_agent_run", fail_create)

    handle = asyncio.run(
        _begin_or_resume_agent_run(
            request=ChatRequest(
                question="期中考试",
                datasource_id=3,
                conversation_id=5,
                agent_mode="agent",
            ),
            current_user_id=1,
            workspace_oid=1,
            persist=True,
        )
    )

    assert handle is not None
    assert handle.is_retry_chat is True
    assert handle.run_id == 12
    assert handle.parent_record_id == 8
    assert len(handle.run_history or []) == 2
    assert calls == {"listed": 1, "created": 0}
