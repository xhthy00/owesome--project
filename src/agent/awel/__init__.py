"""AWEL 极简实现：线性 DAG + Agent 算子。

Phase A 只提供单链执行；Phase C 再引入并行/条件节点与 ``>>`` 语法糖。
"""

from src.agent.awel.dag import LinearDAG
from src.agent.awel.operator import MapOperator, WrappedAgentOperator

__all__ = ["LinearDAG", "MapOperator", "WrappedAgentOperator"]
