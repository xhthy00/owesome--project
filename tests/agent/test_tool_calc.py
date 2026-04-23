"""calculate 工具的行为契约：基本算术正确、危险输入被沙盒拒绝、错误不抛。

为什么安全测试很重要：``calculate`` 是唯一一个"让 LLM 填自由字符串进入求值器"
的工具——任何 asteval 限制的松动都可能直接变成 RCE。所以这里刻意枚举 Python
里典型的注入手段，确保它们都被静默拒绝而不是静默成功。
"""

from __future__ import annotations

import asyncio

from src.agent.resource.tool.calc import calculate


def _call(expr: str):
    return asyncio.run(calculate.execute(expression=expr))


def test_calculate_basic_arithmetic():
    result = _call("1 + 2 * 3")
    assert result.data["value"] == 7
    assert "1 + 2 * 3" in result.content
    assert "7" in result.content


def test_calculate_percentage_growth():
    # 经典 NLSQ 后处理：同比增长率
    result = _call("(1234 - 1000) / 1000 * 100")
    assert abs(result.data["value"] - 23.4) < 1e-6


def test_calculate_rounding_and_math_functions():
    result = _call("round((85 + 92 + 78) / 3, 2)")
    assert result.data["value"] == 85.0

    # asteval 把 math.* 平铺到顶层，LLM 可直接写 sqrt/sin/pi 等
    result = _call("sqrt(2)")
    assert abs(result.data["value"] - 1.41421356) < 1e-6

    result = _call("pi * 2")
    assert abs(result.data["value"] - 6.2831853) < 1e-6


def test_calculate_ternary_expression_allowed():
    """三元是刻意保留的——条件聚合（如"大于 0 返回增长率，否则 0"）很常见。"""
    result = _call("100 if 1 > 0 else 0")
    assert result.data["value"] == 100


def test_calculate_rejects_import():
    result = _call("__import__('os').system('echo pwned')")
    # 不抛，软失败，data.error 含错误信息
    assert "error" in result.data
    assert "value" not in result.data
    assert "calculate 失败" in result.content


def test_calculate_blocks_file_read_via_open():
    """**真实已踩过的坑**：asteval 默认 symtable 里有 ``open``，不删的话
    ``open('/etc/passwd').read()`` 直接把密码文件内容返回给 LLM——等效 RCE。
    Regression test ensures ``open`` 永远不在沙盒里。
    """
    result = _call("open('/etc/passwd').read()")
    assert "error" in result.data, (
        f"致命：open 可调用，calc 已被用作文件读取后门："
        f"content={result.content!r}, data={result.data!r}"
    )
    # 额外强断言：返回里不得出现 /etc/passwd 文件的任何典型字符
    assert "root:" not in result.content
    assert "value" not in result.data


def test_calculate_rejects_reflection_and_exec():
    """其他已知的越狱/反射路径：__subclasses__、exec、dir 等都应拒绝。"""
    for dangerous in (
        "().__class__.__bases__[0].__subclasses__()",
        "exec('print(1)')",
        "dir()",
        "__import__('os').system('echo pwn')",
    ):
        result = _call(dangerous)
        assert "error" in result.data, f"危险输入未被拒绝：{dangerous!r}"
        assert "value" not in result.data, f"危险输入竟有 value：{dangerous!r}"


def test_calculate_rejects_assignment_and_loops():
    """沙盒 minimal 模式应禁控制流/赋值——表达式求值器不需要这些。"""
    for stmt in ("x = 1", "for i in [1,2,3]: pass", "while True: pass"):
        result = _call(stmt)
        assert "error" in result.data, f"非表达式未被拒绝：{stmt!r}"


def test_calculate_empty_expression():
    result = _call("")
    assert "empty" in result.data["error"].lower() or "空" in result.content


def test_calculate_too_long_expression():
    long_expr = "1 + " * 200 + "1"  # 远超 500 字符上限
    result = _call(long_expr)
    assert "too long" in result.data["error"].lower() or "长度" in result.content


def test_calculate_syntax_error_soft_failure():
    """LLM 写错（括号不匹配等）应得到可读错误、不抛，好让它 ReAct 下一轮修正。"""
    result = _call("1 + (2 *")
    assert "error" in result.data
    assert "calculate 失败" in result.content


def test_calculate_isolated_between_calls():
    """每次调用独立 Interpreter，不能跨调用共享变量（防串扰）。

    虽然沙盒禁了赋值，但 asteval 即便静默忽略不该接受的语句，新 interpreter
    的 symbol table 仍必须是干净的；否则上一次 ``x = 1``（如果沙盒有漏洞）
    会被下一次 ``x * 2`` 引用。这里反向断言：即便第一次表达式被拒，第二次
    引用 ``x`` 也应得到 "name error"。
    """
    _call("x = 1")
    result = _call("x * 2")
    assert "error" in result.data, "第一次调用的符号泄漏到第二次调用"
