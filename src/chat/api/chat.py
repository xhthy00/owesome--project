"""Chat API routes based on SQLBot patterns."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging

from common.core.database import get_session
from common.exceptions.base import NotFoundException, BadRequestException
from common.schemas.response import success_response
from chat.schemas import ChatRequest, SQLValidationRequest, SQLFormatRequest
from chat.service.sql_generator import SQLGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/generate-sql")
def generate_sql(
    request: ChatRequest,
    session: Session = Depends(get_session),
):
    """
    Generate SQL from natural language question.

    This endpoint:
    1. Fetches the datasource schema
    2. Builds a prompt with schema information using SQLBot patterns
    3. Calls LLM to generate SQL
    4. Validates the generated SQL
    5. Returns the result with chart type and tables info

    Returns:
        JSON with sql, is_valid, error, formatted_sql, tables, chart_type, brief
    """
    generator = SQLGenerator()

    result = generator.generate_sql(
        question=request.question,
        datasource_id=request.datasource_id,
        session=session,
        need_title=True,
    )

    if not result["is_valid"]:
        return success_response(
            data={
                "sql": result["sql"],
                "is_valid": False,
                "error": result["error"],
                "formatted_sql": "",
                "tables": result.get("tables", []),
                "chart_type": result.get("chart_type", "table"),
                "brief": result.get("brief", ""),
            },
            message="SQL generation failed"
        )

    return success_response(
        data={
            "sql": result["sql"],
            "is_valid": True,
            "error": "",
            "formatted_sql": result["formatted_sql"],
            "tables": result.get("tables", []),
            "chart_type": result.get("chart_type", "table"),
            "brief": result.get("brief", ""),
        },
        message="SQL generated successfully"
    )


@router.post("/generate-sql-stream")
def generate_sql_stream(
    request: ChatRequest,
    session: Session = Depends(get_session),
):
    """
    Generate SQL with streaming response.

    This endpoint generates SQL and streams the response.
    Note: For full streaming implementation, use SSE with the chat endpoint.
    """
    generator = SQLGenerator()

    result = generator.generate_sql(
        question=request.question,
        datasource_id=request.datasource_id,
        session=session,
        need_title=True,
    )

    if not result["is_valid"]:
        raise BadRequestException(result["error"])

    return success_response(
        data={
            "sql": result["sql"],
            "formatted_sql": result["formatted_sql"],
            "tables": result.get("tables", []),
            "chart_type": result.get("chart_type", "table"),
            "brief": result.get("brief", ""),
        },
        message="SQL generated successfully"
    )


@router.post("/execute-sql")
def execute_sql(
    request: ChatRequest,
    session: Session = Depends(get_session),
):
    """
    Generate and execute SQL from natural language question.

    This endpoint:
    1. Generates SQL using LLM with SQLBot patterns
    2. Executes the SQL on the target database
    3. Returns the results

    Returns:
        JSON with sql, error, result (columns, rows, row_count)
    """
    from datasource.crud import crud_datasource
    from datasource.db.db import execute_sql as db_execute_sql
    from common.utils.aes import decrypt_conf

    # Get datasource
    datasource = crud_datasource.get_datasource_by_id(session, request.datasource_id)
    if not datasource:
        raise NotFoundException("Datasource not found")

    config = decrypt_conf(datasource.configuration) if datasource.configuration else {}

    # Generate SQL
    generator = SQLGenerator()
    result = generator.generate_sql(
        question=request.question,
        datasource_id=request.datasource_id,
        session=session,
        need_title=False,
    )

    if not result["is_valid"]:
        return success_response(
            data={
                "sql": result["sql"],
                "error": result["error"],
                "result": None,
                "tables": result.get("tables", []),
                "chart_type": result.get("chart_type", "table"),
            },
            message="SQL generation failed"
        )

    # Execute SQL
    success, message, exec_result = db_execute_sql(
        db_type=datasource.type,
        config=config,
        sql=result["sql"],
    )

    if not success:
        return success_response(
            data={
                "sql": result["sql"],
                "error": message,
                "result": None,
                "tables": result.get("tables", []),
                "chart_type": result.get("chart_type", "table"),
            },
            message="SQL execution failed"
        )

    return success_response(
        data={
            "sql": result["sql"],
            "error": "",
            "result": exec_result,
            "tables": result.get("tables", []),
            "chart_type": result.get("chart_type", "table"),
        },
        message="Query executed successfully"
    )


@router.post("/validate-sql")
def validate_sql_endpoint(
    request: SQLValidationRequest,
    session: Session = Depends(get_session),
):
    """
    Validate a SQL query without executing it.

    This endpoint validates SQL syntax and security.
    The input should be a SQL query, not a natural language question.
    """
    from chat.utils.sql_validator import validate_sql

    is_valid, error_msg = validate_sql(request.sql)

    return success_response(
        data={
            "is_valid": is_valid,
            "error": error_msg,
        },
        message="SQL validation completed"
    )


@router.post("/format-sql")
def format_sql_endpoint(
    request: SQLFormatRequest,
    session: Session = Depends(get_session),
):
    """
    Format a SQL query for specific database type.

    This endpoint formats SQL with proper indentation and keywords.
    The input should be a SQL query, not a natural language question.
    """
    from chat.utils.sql_validator import format_sql
    from datasource.crud import crud_datasource

    # Get datasource to determine database type
    datasource = None
    if request.datasource_id:
        datasource = crud_datasource.get_datasource_by_id(session, request.datasource_id)

    db_type = datasource.type if datasource else "pg"

    formatted = format_sql(request.sql, db_type)

    return success_response(
        data={
            "original_sql": request.sql,
            "formatted_sql": formatted,
            "db_type": db_type,
        },
        message="SQL formatted successfully"
    )
