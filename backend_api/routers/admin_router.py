"""
FastAPI Admin Router (Enterprise Architecture v5)
Provides system health monitoring, database audit diagnostics, and archival operations.
"""
import time
import uuid
from fastapi import APIRouter, Query, Request
from schemas.common import StandardResponse, ResponseMeta
from schemas.admin import SystemHealthData, EtlHistoryItem, ArchiveCleanupResult
from services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["System Monitoring & Administration"])

def _build_meta(request: Request, start_time: float) -> ResponseMeta:
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    return ResponseMeta(trace_id=trace_id, execution_ms=duration_ms)

@router.get(
    "/health",
    response_model=StandardResponse[SystemHealthData],
    summary="Get real-time system diagnostics and connection pool metrics"
)
async def check_system_health(request: Request):
    start_t = time.perf_counter()
    data = AdminService.get_system_health()
    meta = _build_meta(request, start_t)
    return StandardResponse(status=data.system_status.lower(), data=data, meta=meta)

@router.get(
    "/etl-history",
    response_model=StandardResponse[list[EtlHistoryItem]],
    summary="Retrieve recent ETL synchronization job audit logs"
)
async def get_etl_history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100, description="Max audit logs to return")
):
    start_t = time.perf_counter()
    data = AdminService.get_etl_job_histories(limit=limit)
    meta = _build_meta(request, start_t)
    return StandardResponse(status="success", data=data, meta=meta)

@router.post(
    "/cleanup/archive",
    response_model=StandardResponse[ArchiveCleanupResult],
    summary="Trigger cold storage cleanup for old inactive records"
)
async def trigger_cold_storage_cleanup(
    request: Request,
    days: int = Query(default=60, ge=7, le=365, description="Retention threshold in days")
):
    start_t = time.perf_counter()
    data = AdminService.trigger_archive_cleanup(days=days)
    meta = _build_meta(request, start_t)
    return StandardResponse(status="success", data=data, meta=meta)
