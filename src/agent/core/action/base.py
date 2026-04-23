"""Action 抽象：Agent 可执行动作的最小契约。

一个 Action 就是 (LLM 生成的意图字符串) -> (结构化执行结果 ActionOutput)
的一次转换，是 Agent 主循环中 thinking -> act 的落点。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ActionOutput(BaseModel):
    """Action 执行后的标准产物，同时承载 review/verify/路由所需的元信息。"""

    content: str = ""
    is_exe_success: bool = True
    view: str | None = None
    action: str | None = None
    thoughts: str | None = None
    observations: str | None = None
    next_speakers: list[str] | None = None
    terminate: bool = False
    have_retry: bool = True
    resource_value: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Action(ABC):
    """Action 抽象基类。子类必须实现 ``run``。

    约定：
    - ``run`` 为协程；无 IO 的动作也请保持 async 签名，便于统一调度。
    - ``run`` 不允许抛异常表达"业务失败"——应返回 ``is_exe_success=False`` 的
      ActionOutput，让主循环进入自修复流程。只有真正的程序错误才抛异常。
    """

    name: str = ""

    @abstractmethod
    async def run(self, ai_message: str, **kwargs: Any) -> ActionOutput:
        """执行动作。

        Args:
            ai_message: LLM thinking 阶段的原始输出。
            **kwargs: 调用方透传的上下文（如 memory、resource 等）。
        """
        raise NotImplementedError
