"""函数签名内省测试。"""

from __future__ import annotations

from typing import Optional

from src.agent.util.function_utils import parse_function_schema


def test_basic_types_and_required():
    def greet(name: str, times: int = 1, formal: bool = False) -> str:
        """Say hi to someone.

        Args:
            name: Person to greet.
            times: How many times.
            formal: Whether to use formal tone.
        """
        return "hi"

    schema = parse_function_schema(greet)
    assert schema["name"] == "greet"
    assert schema["description"].startswith("Say hi")

    by_name = {p["name"]: p for p in schema["parameters"]}
    assert by_name["name"]["type"] == "string"
    assert by_name["name"]["required"] is True
    assert by_name["name"]["description"] == "Person to greet."

    assert by_name["times"]["type"] == "integer"
    assert by_name["times"]["required"] is False
    assert by_name["times"]["default"] == 1

    assert by_name["formal"]["type"] == "boolean"
    assert by_name["formal"]["required"] is False


def test_optional_and_pep604_union():
    def lookup(key: str, hint: str | None = None, tag: Optional[int] = None) -> str:
        return ""

    schema = parse_function_schema(lookup)
    by_name = {p["name"]: p for p in schema["parameters"]}
    assert by_name["hint"]["type"] == "string"
    assert by_name["hint"]["required"] is False
    assert by_name["tag"]["type"] == "integer"
    assert by_name["tag"]["required"] is False


def test_collection_types_and_missing_annotation():
    def pick(items: list, mapping: dict, x) -> list:
        return items

    schema = parse_function_schema(pick)
    by_name = {p["name"]: p for p in schema["parameters"]}
    assert by_name["items"]["type"] == "array"
    assert by_name["mapping"]["type"] == "object"
    assert by_name["x"]["type"] == "string"


def test_ignores_self_and_var_args():
    class C:
        def m(self, x: int, *args, **kwargs) -> None:
            pass

    schema = parse_function_schema(C.m)
    names = [p["name"] for p in schema["parameters"]]
    assert names == ["x"]
