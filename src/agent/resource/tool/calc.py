"""calc 工具：在 Agent 手里提供一把"受限安全的算术计算器"。

设计取舍
--------
- **为什么要独立工具而不让 LLM 心算**：LLM 在 10 位以上的小数、百分比、同比/
  环比等场景常算错；把这类需求从 LLM 的 token 生成里剥离给 asteval，结论可验证；
- **为什么用 asteval 而不是 ``eval``**：``eval`` 可以 ``__import__('os').system(...)``
  一键命令执行；asteval 基于 AST 白名单，默认禁 import、attribute 访问（dunder
  即被拦）、绝大多数语句节点，AST 级别上严格很多；
- **为什么每次调用都新建 Interpreter**：asteval Interpreter 是有状态的——上一
  次调用定义的变量会留在 symbol table，不隔离就会出现"LLM 偷偷给 x 赋值，下
  次 calculate 算的是旧 x"的并发串扰。

沙盒加固（实测踩坑记录）
-----------------------
asteval 1.0 即使 ``minimal=True`` 也会：

1. 若环境装了 numpy，自动把 numpy 顶层 namespace（``fromfile`` / ``loadtxt``
   / ``fromstring`` 等）注入 symbol table——这些函数**能读任意文件**；
2. 即便 ``use_numpy=False``，默认 symtable 里仍有 ``open`` 和 ``dir``——本地
   ``calculate("open('/etc/passwd').read()")`` 直接把用户密码文件的内容返给
   LLM（等价于 RCE）。

所以 :func:`_safe_interpreter` 必须：(a) 传 ``use_numpy=False`` 禁 numpy；
(b) 显式从 symtable 里删除一组**已知危险**的符号（文件 I/O、反射、进程控制、
构造越狱链路的 builtin 等）。**黑名单容易漏**，但 asteval 的属性访问是白
名单（dunder 被 ``no safe attribute`` 拒绝，已实测），所以只要把能直接调用的
危险函数名清掉，单层调用就没路。后续升级 asteval 版本要重新 probe。

不抛原则
--------
对齐其他业务工具：**表达式错误不抛**，返回 ``ToolResult(success-ish content)``，
让 LLM 在 ReAct 的 observation 里自修正（改写表达式再试）。只有"asteval 本身
构造失败"这种框架错误才抛。
"""

from __future__ import annotations

from typing import Any

from src.agent.resource.tool.base import ToolResult
from src.agent.resource.tool.function_tool import tool

_MAX_EXPR_LEN = 500

#: asteval 默认 symtable 里**必须移除**的符号——能读文件 / 反射 / 造越狱链的都在此。
#: 其中 ``open`` / ``dir`` 是 probe 实测为"默认存在且可调用"的两个真实风险点；
#: 其余（``__import__`` / ``exec`` 等）在当前 asteval 版本的 ``minimal=True`` 下
#: 已不在 symtable，但显式再 pop 一次是为了防 asteval 版本升级时的 **静默回归**。
_BLOCKED_SYMBOLS: frozenset[str] = frozenset({
    "open",         # 文件 I/O
    "dir",          # 反射 symtable
    "__import__",
    "exec", "eval", "compile",
    "input",
    "exit", "quit", "breakpoint",
    "help", "copyright", "credits", "license",
    "getattr", "setattr", "delattr", "hasattr",
    "vars", "globals", "locals",
    "memoryview", "bytearray", "bytes",  # 可构造任意字节绕过字符串限制
    "object", "super",  # 可能被用来走 __subclasses__ 越狱
    "classmethod", "staticmethod", "property",
    "__build_class__",
})


def _safe_interpreter() -> Any:
    """构造受限 asteval Interpreter。

    - ``minimal=True``：摘掉绝大多数语句节点（import / class / with / try / ...）；
    - ``use_numpy=False``：防 numpy I/O 函数（``fromfile`` / ``loadtxt``）进 symtable；
    - 手动 pop :data:`_BLOCKED_SYMBOLS`：清掉默认仍存在的 ``open`` / ``dir`` 等危险符号。
    """
    from asteval import Interpreter

    interp = Interpreter(
        minimal=True,
        use_numpy=False,
        no_if=True,
        no_for=True,
        no_while=True,
        no_try=True,
        no_functiondef=True,
        no_ifexp=False,  # 允许三元 a if b else c —— 计算常用
        no_listcomp=True,
        no_augassign=True,
        no_assert=True,
        no_delete=True,
        no_raise=True,
        no_print=True,
        with_import=False,
        with_importfrom=False,
    )
    for name in _BLOCKED_SYMBOLS:
        interp.symtable.pop(name, None)
    return interp


@tool()
def calculate(expression: str) -> ToolResult:
    """在受限沙盒里求算术表达式的值。

    **适用场景**：百分比、同比/环比、均值、加权求和、简单单位换算等"给定数据
    后的后处理算术"。例如：

        calculate("(1234 - 1000) / 1000 * 100")    # 同比 +23.4%
        calculate("round((85 + 92 + 78) / 3, 2)")  # 平均分 85.0
        calculate("sqrt(2)")                       # √2（math 函数已平铺到顶层）

    **不适用**：涉及取数（用 execute_sql）、字符串处理、日期运算（暂无日期
    支持，可用数值替代）。

    Args:
        expression: Python 表达式字符串。长度 ≤ 500 字符；不支持赋值/循环/
            import/属性访问/文件 I/O；可直接使用 math 顶层函数与常量
            （sin/cos/sqrt/log/pow/pi/e/...）。

    Returns:
        成功：``content`` 为人类可读的结果字符串，``data`` 为 ``{"value": <原始
        数值>, "expression": <输入>}``；失败（表达式无效 / asteval error）：
        ``content`` 含错误说明，``data`` 含 ``error`` 字段，**不抛**。
    """
    expr = (expression or "").strip()
    if not expr:
        return ToolResult(
            content="calculate 失败：expression 不能为空。",
            data={"error": "empty expression", "expression": expression},
        )
    if len(expr) > _MAX_EXPR_LEN:
        return ToolResult(
            content=f"calculate 失败：表达式长度 {len(expr)} 超过上限 {_MAX_EXPR_LEN}，请拆分计算。",
            data={"error": "expression too long", "expression": expr[:80] + "..."},
        )

    aeval = _safe_interpreter()
    value = aeval(expr, show_errors=False)

    if aeval.error:
        err_texts = [str(e.get_error()[1]) for e in aeval.error] or ["unknown error"]
        err_msg = "; ".join(err_texts)
        return ToolResult(
            content=f"calculate 失败：{err_msg}。请检查表达式是否只用算术运算与 math.* 函数。",
            data={"error": err_msg, "expression": expr},
        )

    if value is None:
        return ToolResult(
            content="calculate 失败：表达式无返回值（可能是赋值/控制流，已被沙盒拒绝）。",
            data={"error": "no value", "expression": expr},
        )

    return ToolResult(
        content=f"计算结果：`{expr}` = **{value}**",
        data={"value": value, "expression": expr},
    )


__all__ = ["calculate"]
