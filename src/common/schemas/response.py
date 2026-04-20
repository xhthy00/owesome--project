"""Unified API response schemas."""

from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseBase(BaseModel):
    """Base response model."""
    code: int = Field(default=200, description="Response code, 200=success")
    message: str = Field(default="success", description="Response message")


class ResponseModel(ResponseBase, Generic[T]):
    """Generic response model with data."""
    data: Optional[T] = Field(None, description="Response data")

    class Config:
        from_attributes = True


class PageData(BaseModel, Generic[T]):
    """Paginated data."""
    items: List[T] = Field(default_factory=list, description="Data items")
    total: int = Field(default=0, description="Total count")
    page: int = Field(default=1, description="Current page")
    page_size: int = Field(default=20, description="Page size")


class PageResponse(ResponseBase):
    """Paginated response."""
    data: PageData = Field(..., description="Paginated data")


class ListResponse(ResponseBase, Generic[T]):
    """List response."""
    data: List[T] = Field(default_factory=list, description="List data")


class ErrorDetail(BaseModel):
    """Error detail model."""
    field: Optional[str] = Field(None, description="Field that caused error")
    message: str = Field(..., description="Error message")


def success_response(data: Any = None, message: str = "success") -> dict:
    """Create a success response."""
    return {
        "code": 200,
        "message": message,
        "data": data,
    }


def error_response(code: int = 400, message: str = "error", data: Any = None) -> dict:
    """Create an error response."""
    return {
        "code": code,
        "message": message,
        "data": data,
    }