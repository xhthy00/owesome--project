"""Configuration management using pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_name: str = "awesome-project"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/awesome"

    # JWT
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # LLM
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: str = "gpt-4o-mini"
    # 单次请求输出上限。不设置时各服务商默认值不一（MiniMax 等偏小），长 <think>
    # + 工具调用 JSON 会被中途截断，导致 ReAct 解析连续失败。显式给宽裕值。
    llm_max_tokens: int = 8192
    # 思考模式控制：``disabled`` / ``adaptive``。仅部分模型支持（如 MiniMax-M3；
    # M2.x 不可关闭）。留空不发送该参数，其他网关（GLM/Qwen 等）不受影响。
    llm_thinking: Optional[str] = None

    # Team 模式编排：``legacy`` 为手写协程；``langgraph`` 为 LangGraph StateGraph（默认）。
    team_orchestrator: Literal["legacy", "langgraph"] = "langgraph"

    # 多轮对话：按用户提问轮数截取 chat_log 历史（对齐 SQLBot GENERATE_SQL_QUERY_HISTORY_ROUND_COUNT）
    generate_sql_query_history_round_count: int = 3

    # 教育澄清：用 LLM 抽取意图槽位（对标 DB-GPT IntentDetection）。关掉则只走规则抽槽。
    edu_llm_slot_extraction: bool = True



@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
