"""Agent 短期记忆：最简内存环形队列。

Phase A 目标是"跑通主循环"，所以只做最小可用版本：
- 单 Agent 进程内记忆，不持久化；
- 不做向量检索，``read`` 直接返回最近 N 条；
- 后续 Phase D 会替换为 GptsMemory（DB 持久化 + 跨 Agent 共享）。
"""

from __future__ import annotations

import asyncio
from typing import Any


class AgentMemory:
    def __init__(self, max_size: int = 50) -> None:
        self._store: list[dict[str, Any]] = []
        self._max_size = max_size
        self._lock = asyncio.Lock()

    async def write(self, fragment: dict[str, Any]) -> None:
        async with self._lock:
            self._store.append(fragment)
            overflow = len(self._store) - self._max_size
            if overflow > 0:
                self._store = self._store[overflow:]

    async def read(self, query: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        async with self._lock:
            items = list(self._store)
        if limit is not None:
            items = items[-limit:]
        return items

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
