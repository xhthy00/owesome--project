"""Agent Profile：描述一个 Agent 的静态身份与行为边界。

设计原则：
- 纯数据，不包含运行时状态。
- 字段保持克制，随 Agent 类型演进再扩展（expand_prompt / examples 等）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProfileConfig:
    """Agent 的身份卡。

    Attributes:
        name: Agent 名称，全局唯一，用于在多 Agent 协作中识别发送者。
        role: 角色标签（如 "DataAnalyst"），用于 prompt 自我介绍与路由。
        goal: 目标描述，写入 system prompt 的首段。
        constraints: 硬约束列表，写入 system prompt 的约束段。
        desc: 可选补充说明，追加在 prompt 末尾。
    """

    name: str
    role: str
    goal: str = ""
    constraints: list[str] = field(default_factory=list)
    desc: str = ""

    def render_system_prompt(self, variables: dict[str, object] | None = None) -> str:
        """按固定结构拼出 system prompt，并用 {{var}} 做最小模板替换。"""
        parts: list[str] = [f"你是 {self.name}（角色：{self.role}）。"]
        if self.goal:
            parts.append(f"目标：{self.goal}")
        if self.constraints:
            bullets = "\n".join(f"- {c}" for c in self.constraints)
            parts.append(f"约束：\n{bullets}")
        if self.desc:
            parts.append(self.desc)

        prompt = "\n\n".join(parts)
        if variables:
            for k, v in variables.items():
                prompt = prompt.replace("{{" + k + "}}", str(v))
        return prompt
