"""SQL generation service based on SQLBot patterns."""

from typing import Dict, List, Optional, Any
import logging
import json
import re

from src.llm.service import create_llm, build_chat_messages
from src.templates.sql_gen_prompt import (
    build_sql_generation_prompt,
    build_schema_info,
    parse_llm_sql_response,
)
from src.chat.utils.sql_validator import validate_sql, extract_sql, format_sql
from src.common.utils.aes import decrypt_conf

logger = logging.getLogger(__name__)


class SQLGenerator:
    """Service for generating SQL from natural language based on SQLBot patterns."""

    def __init__(self, llm=None):
        self.llm = llm or create_llm()

    def generate_sql(
        self,
        question: str,
        datasource_id: int,
        session,
        instructions: str = "",
        terminologies: str = "",
        data_training: str = "",
        custom_prompt: str = "",
        need_title: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate SQL from natural language question.

        Args:
            question: User's natural language question
            datasource_id: ID of the datasource to query
            session: Database session for fetching schema
            instructions: Additional instructions for the LLM
            terminologies: Terminology definitions
            data_training: SQL training examples
            custom_prompt: Custom prompt information
            need_title: Whether to generate conversation title

        Returns:
            Dict with keys: sql, is_valid, error, formatted_sql, tables, chart_type, brief
        """
        # 1. Get datasource and decrypt config
        from src.datasource.crud import crud_datasource

        datasource = crud_datasource.get_datasource_by_id(session, datasource_id)
        if not datasource:
            return {
                "sql": "",
                "is_valid": False,
                "error": f"Datasource {datasource_id} not found",
                "formatted_sql": "",
                "tables": [],
                "chart_type": "table",
                "brief": "",
            }

        config = decrypt_conf(datasource.configuration) if datasource.configuration else {}
        db_type = datasource.type or "pg"

        # 2. Get schema information from database
        schema_info = self._get_schema(session, datasource, config, db_type)

        # 3. Build prompt using SQLBot templates
        system_prompt, user_prompt = build_sql_generation_prompt(
            question=question,
            database_type=db_type,
            schema_info=schema_info,
            instructions=instructions,
            terminologies=terminologies,
            data_training=data_training,
            custom_prompt=custom_prompt,
            error_msg="",
            need_title=need_title,
        )

        # 4. Call LLM
        try:
            messages = build_chat_messages(system_prompt, user_prompt)
            raw_response = self.llm.chat(messages)
            logger.info(f"LLM raw response length: {len(raw_response)}")
            logger.info(f"LLM raw response: {raw_response[:1000]}")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {
                "sql": "",
                "is_valid": False,
                "error": f"LLM call failed: {str(e)}",
                "formatted_sql": "",
                "tables": [],
                "chart_type": "table",
                "brief": "",
            }

        # 5. Parse LLM response using SQLBot-style JSON parsing
        parse_result = parse_llm_sql_response(raw_response)

        if not parse_result.get("success", False):
            return {
                "sql": "",
                "is_valid": False,
                "error": parse_result.get("message", "Failed to generate SQL"),
                "formatted_sql": "",
                "tables": [],
                "chart_type": "table",
                "brief": "",
            }

        # 6. Extract and validate SQL
        sql = extract_sql(parse_result.get("sql", ""))
        is_valid, error_msg = validate_sql(sql)

        if not is_valid:
            return {
                "sql": sql,
                "is_valid": False,
                "error": error_msg,
                "formatted_sql": "",
                "tables": parse_result.get("tables", []),
                "chart_type": parse_result.get("chart_type", "table"),
                "brief": parse_result.get("brief", ""),
            }

        # 7. Format SQL
        formatted_sql = format_sql(sql, db_type)

        return {
            "sql": sql,
            "is_valid": True,
            "error": "",
            "formatted_sql": formatted_sql,
            "tables": parse_result.get("tables", []),
            "chart_type": parse_result.get("chart_type", "table"),
            "brief": parse_result.get("brief", ""),
        }

    def generate_sql_with_retry(
        self,
        question: str,
        datasource_id: int,
        session,
        max_retries: int = 2,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate SQL with automatic retry on failure.

        Args:
            question: User's natural language question
            datasource_id: ID of the datasource to query
            session: Database session
            max_retries: Maximum number of retry attempts
            **kwargs: Additional arguments passed to generate_sql

        Returns:
            Dict with keys: sql, is_valid, error, formatted_sql, tables, chart_type, brief
        """
        result = self.generate_sql(question, datasource_id, session, **kwargs)

        retry_count = 0
        while not result["is_valid"] and retry_count < max_retries:
            logger.info(f"SQL generation failed, retry {retry_count + 1}/{max_retries}")

            # Build error message for retry
            error_msg = result.get("error", "")

            # Get datasource and config
            from src.datasource.crud import crud_datasource
            datasource = crud_datasource.get_datasource_by_id(session, datasource_id)
            if not datasource:
                break

            config = decrypt_conf(datasource.configuration) if datasource.configuration else {}
            db_type = datasource.type or "pg"
            schema_info = self._get_schema(session, datasource, config, db_type)

            # Retry with error message
            result = self.generate_sql(
                question=question,
                datasource_id=datasource_id,
                session=session,
                custom_prompt=f"请注意：你之前生成的SQL有误，错误原因：{error_msg}。请重新生成。",
                **kwargs
            )
            retry_count += 1

        return result

    def _get_schema(
        self,
        session,
        datasource,
        config: Dict,
        db_type: str,
    ) -> str:
        """
        Get database schema information.

        Returns formatted schema string for prompt.
        """
        from src.datasource.db.db import get_schema_info

        try:
            tables = get_schema_info(db_type, config)
            return build_schema_info(tables, db_type)
        except Exception as e:
            logger.warning(f"Failed to get schema: {e}")
            return "Schema information not available."


def generate_followup_questions(
    question: str,
    schema_info: str,
    old_questions: List[str] = None,
    articles_number: int = 5,
    lang: str = "zh"
) -> List[str]:
    """
    Generate follow-up question suggestions based on SQLBot patterns.

    Args:
        question: Current user question
        schema_info: Database schema information
        old_questions: Previous user questions
        articles_number: Number of suggestions to generate
        lang: Language for response

    Returns:
        List of suggested follow-up questions
    """
    try:
        llm = create_llm()

        system_prompt = f"""### 请使用语言：{lang} 回答，不需要输出深度思考过程

### 说明：
您的任务是根据给定的表结构，用户问题以及以往用户提问，推测用户接下来可能提问的1-{articles_number}个问题。
请遵循以下规则：
- 推测的问题需要与提供的表结构相关，生成的提问例子如：["查询所有用户数据","使用饼图展示各产品类型的占比","使用折线图展示销售额趋势",...]
- 推测问题如果涉及图形展示，支持的图形类型为：表格(table)、柱状图(column)、条形图(bar)、折线图(line)或饼图(pie)
- 推测的问题不能与当前用户问题重复
- 推测的问题必须与给出的表结构相关
- 若有以往用户提问列表，则根据以往用户提问列表，推测用户最频繁提问的问题，加入到你生成的推测问题中
- 忽略"重新生成"相关的问题
- 如果用户没有提问且没有以往用户提问，则仅根据提供的表结构推测问题
- 生成的推测问题使用JSON格式返回：
["推测问题1", "推测问题2", "推测问题3", "推测问题4"]
- 最多返回{articles_number}个你推测出的结果
- 若无法推测,则返回空数据JSON:
[]
- 若你的给出的JSON不是{lang}的，则必须翻译为{lang}

### 响应, 请直接返回JSON结果（不要包含任何其他文本）："""

        old_questions_str = json.dumps(old_questions, ensure_ascii=False) if old_questions else "[]"

        user_prompt = f"""### 表结构:
{schema_info}

### 当前问题:
{question}

### 以往提问:
{old_questions_str}

/no_think"""

        messages = build_chat_messages(system_prompt, user_prompt)
        response = llm.chat(messages)

        # Parse JSON response
        suggestions = json.loads(response)
        if isinstance(suggestions, list):
            return suggestions
        return []

    except Exception as e:
        logger.error(f"Failed to generate follow-up questions: {e}")
        return []
