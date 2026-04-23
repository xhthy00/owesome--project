"""``src.common.core.trace`` 单测。

本测试关注三件事（每件都有明确的失败信号）：

1. ``new_trace_id()`` 生成的 id 是**非空、合理长度、随机**的——避免"永远返回同一个值"。
2. ``trace_scope()`` 是 **async/thread-safe** 的——两个并发协程 / 子线程不会互相污染。
3. ``install_trace_log_factory()`` 把 trace_id 挂到 ``LogRecord`` 上——
   既生效、又幂等、也不吞掉其他代码用 ``extra={"trace_id": ...}`` 的显式值。

测试里**不去动全局 logging 配置**，只在本测试作用域内增加一个 handler，结束就移除，
避免污染其他测试的 caplog。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from io import StringIO

from src.common.core.trace import (
    _reset_factory_for_testing,
    get_trace_id,
    install_trace_log_factory,
    new_trace_id,
    set_trace_id,
    trace_scope,
)


def test_new_trace_id_is_nonempty_and_random() -> None:
    ids = {new_trace_id() for _ in range(200)}
    assert len(ids) == 200, "200 次生成出现碰撞，随机性不足"
    for tid in list(ids)[:10]:
        assert isinstance(tid, str)
        assert 8 <= len(tid) <= 32
        assert tid != "-"


def test_get_trace_id_defaults_to_dash_outside_scope() -> None:
    assert get_trace_id() == "-"


def test_trace_scope_sets_and_restores() -> None:
    assert get_trace_id() == "-"
    with trace_scope("alpha") as tid:
        assert tid == "alpha"
        assert get_trace_id() == "alpha"
        with trace_scope("beta") as inner:
            assert inner == "beta"
            assert get_trace_id() == "beta"
        assert get_trace_id() == "alpha", "内层 scope 退出后必须还原到外层 id"
    assert get_trace_id() == "-", "scope 全部退出后必须恢复默认"


def test_trace_scope_auto_generates_when_no_arg() -> None:
    with trace_scope() as tid:
        assert tid != "-"
        assert get_trace_id() == tid


def test_trace_id_isolated_between_concurrent_tasks() -> None:
    """两个并发 task 各自的 trace_id 不会互相污染——ContextVar 的核心承诺。

    用 ``asyncio.run`` 而不是 pytest-asyncio——后者不在项目 dev 依赖里。
    """

    async def worker(tid: str, delay: float) -> str:
        with trace_scope(tid):
            await asyncio.sleep(delay)
            return get_trace_id()

    async def _gather() -> list[str]:
        return await asyncio.gather(
            worker("task-A", 0.02),
            worker("task-B", 0.01),
            worker("task-C", 0.03),
        )

    results = asyncio.run(_gather())
    assert results == ["task-A", "task-B", "task-C"]


def test_trace_id_propagates_through_asyncio_to_thread() -> None:
    """``asyncio.to_thread`` 内部用 ``contextvars.copy_context`` 派发，trace_id
    必须跟随到被 offload 的线程；这是 runner 里 DB 持久化等同步操作能拿到 trace_id 的前提。
    """

    async def outer() -> str:
        with trace_scope("threaded"):
            return await asyncio.to_thread(get_trace_id)

    got = asyncio.run(outer())
    assert got == "threaded"


def test_trace_id_not_shared_across_bare_threads_without_scope() -> None:
    """反面测试：如果子线程没通过 copy_context，trace_id 不会跨线程传播。

    这一条是为了**固化行为边界**——以后如果改成全局变量，这个测试就会挂掉，
    提醒我们破坏了 per-request 隔离。
    """
    set_trace_id("main-thread")
    captured: list[str] = []

    def worker() -> None:
        captured.append(get_trace_id())

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert captured == ["-"]
    # 收尾：把主线程的 trace_id 复位，避免污染后续测试
    set_trace_id("-")


def test_install_trace_log_factory_injects_trace_id_and_is_idempotent() -> None:
    _reset_factory_for_testing()
    try:
        install_trace_log_factory()
        install_trace_log_factory()  # 第二次调用应被忽略，不会双重包装

        logger = logging.getLogger("test.trace.factory")
        buf = StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(
            logging.Formatter("%(trace_id)s|%(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        try:
            with trace_scope("injected-tid"):
                logger.info("hello")
            logger.info("no-scope")
        finally:
            logger.removeHandler(handler)
            logger.propagate = True

        lines = [line for line in buf.getvalue().splitlines() if line]
        assert lines == ["injected-tid|hello", "-|no-scope"], (
            f"log factory 未正确注入 trace_id；实际输出={lines!r}"
        )
    finally:
        # 重置 flag，让其他测试（或重复运行本测试）仍可覆盖到 install
        _reset_factory_for_testing()


def test_install_trace_log_factory_renders_default_when_outside_scope() -> None:
    """无任何 scope 时，log format 中的 ``%(trace_id)s`` 应渲染为 ``-``，而不是
    报 ``KeyError`` / 空值——这保证第三方模块的日志不会因为缺字段而炸掉。
    """
    _reset_factory_for_testing()
    try:
        install_trace_log_factory()
        logger = logging.getLogger("test.trace.factory.default")
        buf = StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(logging.Formatter("%(trace_id)s|%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        try:
            logger.info("outside")
        finally:
            logger.removeHandler(handler)
            logger.propagate = True

        assert buf.getvalue().strip() == "-|outside"
    finally:
        _reset_factory_for_testing()
