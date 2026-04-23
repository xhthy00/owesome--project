"""ResourceManager：进程内 ``pack_name → ToolPack`` 的注册表。

设计初衷
--------
目前 Agent 取工具的入口只有 ``build_default_toolpack()`` 一条；日后要加：

1. ToolAgent 这种"工具专家 Agent"需要指定 pack 名拿工具集（比如
   ``calc_only`` / ``search_only``）；
2. 管理端可能需要列出系统当前**注册过的** pack 名做只读可视化；
3. Planner 分派 sub_task 到某类 agent 时，也可能通过 pack 名告知目标 agent
   "你能用哪些工具"。

ResourceManager 就是把"Python 模块里散落的工厂函数"统一收纳到一个**可按名取
出**的位置——仅此而已。**不**做 DB 持久化（按决策推迟到 Phase G），**不**做
动态加载（不需要），**不**自动发现插件（需要时再加）。

并发模型
--------
- 单例 ``_INSTANCE``，进程生命周期；
- 注册（``register_pack``）只发生在应用启动时和测试 setup 里，运行时只读
  （``get_pack``）。所以内部 ``_packs`` 字典**不加锁**——多读单写无风险；
- ``install_default_resources`` **幂等**：重复调用不会报错也不会重复注册。

与 ``build_default_toolpack`` 的关系
------------------------------------
注册的是**未绑定的模板 pack**：``datasource_id`` / ``user_id`` 由调用方
运行时 ``.bind(...)`` 产生新 pack，模板 pack 永远只读共享。这样单进程多请求
之间不会互相污染。
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agent.resource.tool.pack import ToolPack

logger = logging.getLogger(__name__)

#: 默认业务 pack 的注册名——Agent 工厂默认取它。
DEFAULT_PACK_NAME = "default"


class PackAlreadyRegisteredError(ValueError):
    """pack_name 重名——强提示以防静默覆盖。"""


class PackNotFoundError(KeyError):
    """``get_pack`` 请求一个未注册的名字。"""


class ResourceManager:
    """进程内 ToolPack 注册表。仅保存未绑定的模板 pack（参见模块 docstring）。"""

    def __init__(self) -> None:
        self._packs: dict[str, ToolPack] = {}

    def register_pack(self, name: str, pack: "ToolPack", *, replace: bool = False) -> None:
        """注册一个 pack。``replace=False`` 时重名抛 :class:`PackAlreadyRegisteredError`。

        Args:
            replace: 测试里有时想覆盖重注册，显式传 ``True``；生产代码不应传。
        """
        if not name:
            raise ValueError("pack name must be non-empty")
        if name in self._packs and not replace:
            raise PackAlreadyRegisteredError(
                f"pack {name!r} already registered; pass replace=True to overwrite"
            )
        self._packs[name] = pack
        logger.info(
            "ResourceManager: registered pack %r with %d tool(s) [%s]",
            name,
            len(pack),
            ", ".join(pack.names()),
        )

    def get_pack(self, name: str = DEFAULT_PACK_NAME) -> "ToolPack":
        if name not in self._packs:
            raise PackNotFoundError(
                f"pack {name!r} not registered; known: {sorted(self._packs)}"
            )
        return self._packs[name]

    def has_pack(self, name: str) -> bool:
        return name in self._packs

    def list_packs(self) -> list[str]:
        return sorted(self._packs.keys())

    def clear(self) -> None:
        """**仅供测试**使用：清空注册表以保证跨测试隔离。"""
        self._packs.clear()


_INSTANCE: ResourceManager | None = None
_LOCK = threading.Lock()


def get_resource_manager() -> ResourceManager:
    """返回进程单例。首次调用时**懒构造**——不依赖任何启动顺序，测试友好。"""
    global _INSTANCE
    if _INSTANCE is None:
        with _LOCK:
            if _INSTANCE is None:
                _INSTANCE = ResourceManager()
    return _INSTANCE


def install_default_resources() -> None:
    """把 ``default`` pack 注册到单例。**幂等**——重复调用不会报错也不覆盖。

    期望在 FastAPI ``lifespan`` 启动阶段调用一次；测试也可以主动调用。
    """
    from src.agent.resource.tool.business import build_default_toolpack

    mgr = get_resource_manager()
    if mgr.has_pack(DEFAULT_PACK_NAME):
        # 幂等：lifespan 重入、热重载场景下都不应噪音抛错
        logger.debug("default pack already registered, skip")
        return
    # 模板 pack 不带运行时 bindings——调用方自己 .bind(datasource_id=..., user_id=...)
    template = build_default_toolpack(
        datasource_id=None,
        user_id=None,
        include_terminate=True,
    )
    mgr.register_pack(DEFAULT_PACK_NAME, template)


__all__ = [
    "DEFAULT_PACK_NAME",
    "PackAlreadyRegisteredError",
    "PackNotFoundError",
    "ResourceManager",
    "get_resource_manager",
    "install_default_resources",
]
