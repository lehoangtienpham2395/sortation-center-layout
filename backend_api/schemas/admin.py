"""
Pydantic v2 Schemas for Admin & Monitoring Endpoints (Enterprise Architecture v5)
Defines response structures for health diagnostics, ETL job audit logs, and database cleanup.
"""
from pydantic import BaseModel, Field

class ConnectionPoolStatus(BaseModel):
    """Real-time ThreadedConnectionPool diagnostics."""
    status: str = Field(default="HEALTHY")
    minconn: int
    maxconn: int
    active_used_connections: int
    available_connections: int
    pool_usage_percent: float

class SystemHealthData(BaseModel):
    """Payload returned by GET /api/v1/admin/health"""
    system_status: str = Field(default="OK", description="OK | WARNING | ERROR")
    database_connection: str = Field(default="CONNECTED")
    database_size_bytes: int = Field(default=0)
    database_size_human: str = Field(default="0 MB")
    active_shipments_count: int = Field(default=0)
    last_successful_etl_time: str | None = Field(default=None)
    connection_pool: ConnectionPoolStatus

class EtlHistoryItem(BaseModel):
    """Single ETL job audit log item from etl_job_history table."""
    job_id: str
    start_time: str
    end_time: str | None = None
    duration_sec: float | None = None
    status: str
    records_processed: int = 0
    error_message: str | None = None
    triggered_by: str = "CRON"

class ArchiveCleanupResult(BaseModel):
    """Result summary returned after triggering cold storage archive or cleanup."""
    action: str = "CLEANUP_INACTIVE"
    records_deleted: int = 0
    records_archived: int = 0
    execution_duration_sec: float = 0.0
