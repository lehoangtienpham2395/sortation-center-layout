"""
Common Pydantic Schemas & Standard Response Envelope (Enterprise Architecture v5)
Guarantees strict contract adherence across all endpoints.
"""
from typing import Generic, TypeVar, Any
from pydantic import BaseModel, Field
from datetime import datetime
from zoneinfo import ZoneInfo

DataT = TypeVar("DataT")

def current_vnm_timestamp() -> str:
    """Returns ISO 8601 timestamp in Asia/Ho_Chi_Minh time zone."""
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()

class ResponseMeta(BaseModel):
    """Execution metadata included in API response envelope."""
    trace_id: str = Field(..., description="Unique Trace ID of the request")
    execution_ms: float = Field(..., description="Processing duration in milliseconds")
    version: str = Field(default="5.0.0")

class PaginationMeta(ResponseMeta):
    """Extended metadata for paginated list endpoints."""
    current_page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)
    total_records: int = Field(default=0, ge=0)
    total_pages: int = Field(default=0, ge=0)

class StandardResponse(BaseModel, Generic[DataT]):
    """Unified API Response Envelope compliant with Enterprise Architecture v5."""
    status: str = Field(default="success", description="status: success | error | warning")
    timestamp: str = Field(default_factory=current_vnm_timestamp)
    data: DataT | None = Field(default=None, description="Response payload object or list")
    meta: ResponseMeta | PaginationMeta | None = Field(default=None, description="Diagnostic metadata")

class ErrorResponse(BaseModel):
    """Standardized Error Envelope for HTTP exceptions."""
    status: str = Field(default="error")
    timestamp: str = Field(default_factory=current_vnm_timestamp)
    error_code: str = Field(..., description="Internal error code e.g. ERR_POOL_EXHAUSTED")
    message: str = Field(..., description="Human-readable error description")
    detail: Any | None = None
