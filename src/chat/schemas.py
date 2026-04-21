"""Chat schemas for request/response validation."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat request schema for SQL generation."""
    question: str = Field(..., min_length=1, max_length=1000, description="User's natural language question")
    datasource_id: int = Field(..., description="ID of the datasource to query")


class SQLValidationRequest(BaseModel):
    """SQL validation request schema."""
    sql: str = Field(..., min_length=1, max_length=5000, description="SQL query to validate")


class SQLFormatRequest(BaseModel):
    """SQL format request schema."""
    sql: str = Field(..., min_length=1, max_length=5000, description="SQL query to format")
    datasource_id: Optional[int] = Field(None, description="ID of the datasource (for db_type detection)")


class SQLGenerationResult(BaseModel):
    """SQL generation result."""
    sql: str = Field(..., description="Generated SQL query")
    is_valid: bool = Field(..., description="Whether SQL is valid")
    error: str = Field(default="", description="Error message if invalid")
    formatted_sql: str = Field(default="", description="Formatted SQL")
    tables: List[str] = Field(default_factory=list, description="Tables used in SQL")
    chart_type: str = Field(default="table", description="Recommended chart type")
    brief: str = Field(default="", description="Conversation title")


class SQLExecutionResult(BaseModel):
    """SQL execution result."""
    sql: str = Field(..., description="Executed SQL query")
    error: str = Field(default="", description="Error message if failed")
    result: Optional[Dict[str, Any]] = Field(None, description="Query result")
    tables: List[str] = Field(default_factory=list, description="Tables used in SQL")
    chart_type: str = Field(default="table", description="Recommended chart type")


class SQLValidationResult(BaseModel):
    """SQL validation result."""
    is_valid: bool = Field(..., description="Whether SQL is valid")
    error: str = Field(default="", description="Error message if invalid")


class SQLFormatResult(BaseModel):
    """SQL format result."""
    original_sql: str = Field(..., description="Original SQL")
    formatted_sql: str = Field(..., description="Formatted SQL")
    db_type: str = Field(..., description="Database type")
