"""ResourceManager 行为契约。

关注点：
- 注册表的幂等与"重名强报错"语义；
- 单例正确工作；
- ``install_default_resources`` 幂等（lifespan 重入也不炸）；
- ``build_data_analyst`` 能从 manager 取模板再 bind——验证一致性，不验证绑定后
  的 LLM 调用（那是 DataAnalyst 集成测试的职责）。
"""

from __future__ import annotations

import pytest

from src.agent.resource.manager import (
    DEFAULT_PACK_NAME,
    PackAlreadyRegisteredError,
    PackNotFoundError,
    ResourceManager,
    get_resource_manager,
    install_default_resources,
)
from src.agent.resource.tool.business import build_default_toolpack


@pytest.fixture
def fresh_manager():
    """每个测试拿干净 manager——**必须**清掉单例里的 default pack，
    防止 install_default_resources 的幂等缓存干扰断言。"""
    mgr = get_resource_manager()
    mgr.clear()
    yield mgr
    mgr.clear()


def test_register_pack_then_get_pack(fresh_manager: ResourceManager):
    pack = build_default_toolpack()
    fresh_manager.register_pack("myname", pack)
    assert fresh_manager.has_pack("myname")
    assert fresh_manager.get_pack("myname") is pack
    assert "myname" in fresh_manager.list_packs()


def test_register_pack_duplicate_name_raises(fresh_manager: ResourceManager):
    pack = build_default_toolpack()
    fresh_manager.register_pack("x", pack)
    with pytest.raises(PackAlreadyRegisteredError):
        fresh_manager.register_pack("x", build_default_toolpack())


def test_register_pack_replace_true_overwrites(fresh_manager: ResourceManager):
    p1 = build_default_toolpack()
    p2 = build_default_toolpack()
    fresh_manager.register_pack("x", p1)
    fresh_manager.register_pack("x", p2, replace=True)
    assert fresh_manager.get_pack("x") is p2


def test_register_pack_empty_name_raises(fresh_manager: ResourceManager):
    with pytest.raises(ValueError):
        fresh_manager.register_pack("", build_default_toolpack())


def test_get_pack_unknown_raises(fresh_manager: ResourceManager):
    with pytest.raises(PackNotFoundError):
        fresh_manager.get_pack("nope")


def test_get_resource_manager_returns_singleton():
    a = get_resource_manager()
    b = get_resource_manager()
    assert a is b


def test_install_default_resources_is_idempotent(fresh_manager: ResourceManager):
    install_default_resources()
    install_default_resources()  # 再装一次：不应抛，不应重复注册
    assert fresh_manager.has_pack(DEFAULT_PACK_NAME)
    assert fresh_manager.list_packs() == [DEFAULT_PACK_NAME]


def test_install_default_resources_registers_expected_tools(fresh_manager: ResourceManager):
    install_default_resources()
    pack = fresh_manager.get_pack(DEFAULT_PACK_NAME)
    expected = {
        "list_tables",
        "find_related_tables",
        "describe_table",
        "sample_rows",
        "execute_sql",
        "find_related_datasources",
        "recent_questions",
        "calculate",
        "render_html_report",
        "terminate",
    }
    assert set(pack.names()) == expected


def test_install_default_resources_pack_is_unbound(fresh_manager: ResourceManager):
    """模板 pack 必须是**未绑定**的——运行时 .bind 生成新 pack，保持模板只读共享。"""
    install_default_resources()
    pack = fresh_manager.get_pack(DEFAULT_PACK_NAME)
    assert pack.bindings == {}, f"default 模板 pack 不应带 bindings，实际：{pack.bindings}"


def test_build_data_analyst_uses_resource_manager(fresh_manager: ResourceManager):
    """build_data_analyst 应从 ResourceManager 拿模板，再 bind datasource_id。"""
    from src.agent.expand.data_analyst import build_data_analyst

    class _NoopLlm:
        async def chat(self, messages):  # pragma: no cover - 不会被调用
            return ""

    agent = build_data_analyst(
        llm_client=_NoopLlm(),
        datasource_id=42,
        user_id=7,
    )

    # 新产生的 pack 应带正确 bindings
    assert agent.tool_pack.bindings == {"datasource_id": 42, "user_id": 7}
    # 但 manager 里的模板 pack **不**应被污染——这是关键不变式
    template = fresh_manager.get_pack(DEFAULT_PACK_NAME)
    assert template.bindings == {}
    # 工具集内容一致
    assert set(agent.tool_pack.names()) == set(template.names())


def test_build_data_analyst_falls_back_when_manager_has_no_default(fresh_manager: ResourceManager):
    """兜底路径：manager 里没有 default pack 时，build_data_analyst 会自动 install 一次。"""
    from src.agent.expand.data_analyst import build_data_analyst

    class _NoopLlm:
        async def chat(self, messages):  # pragma: no cover
            return ""

    assert not fresh_manager.has_pack(DEFAULT_PACK_NAME)

    agent = build_data_analyst(llm_client=_NoopLlm(), datasource_id=1)

    assert fresh_manager.has_pack(DEFAULT_PACK_NAME), "应静默 install 默认 pack"
    assert agent.tool_pack.bindings == {"datasource_id": 1}
