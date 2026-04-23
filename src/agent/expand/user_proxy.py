"""UserProxyAgent：代表最终用户的最简 sender。

不参与推理、无 Action、无记忆，仅作为消息发送者身份标识出现在主循环参数里。
这让主循环的 ``sender`` 参数有一个可点名的默认值，方便日志追踪与可视化。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UserProxyAgent:
    name: str = "user"
    role: str = "User"
