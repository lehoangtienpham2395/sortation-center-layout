"""
FastAPI Dashboard Router (Enterprise Architecture v5)
Provides aggregated KPIs and paginated details for React Vite SPA.
Strictly delegates all queries to DashboardService without raw SQL.
"""
import time
import uuid
from math import ceil
from fastapi import APIRouter, Query, Request
from schemas.common import StandardResponse, ResponseMeta, PaginationMeta
from schemas.dashboard import InboundDashboardData, OutboundDashboardData, ShipmentDetailItem
from services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard KPIs & Aggregations"])

def _build_meta(request: Request, start_time: float) -> ResponseMeta:
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    return ResponseMeta(trace_id=trace_id, execution_ms=duration_ms)

@router.get(
    "/inbound",
    response_model=StandardResponse[InboundDashboardData],
    summary="Get pre-aggregated Inbound Dashboard data (< 50ms P50)"
)
async def get_inbound_dashboard(request: Request):
    start_t = time.perf_counter()
    data = DashboardService.get_inbound_dashboard()
    meta = _build_meta(request, start_t)
    return StandardResponse(status="success", data=data, meta=meta)

@router.get(
    "/outbound",
    response_model=StandardResponse[OutboundDashboardData],
    summary="Get pre-aggregated Outbound Dashboard data (< 50ms P50)"
)
async def get_outbound_dashboard(request: Request):
    start_t = time.perf_counter()
    data = DashboardService.get_outbound_dashboard()
    meta = _build_meta(request, start_t)
    return StandardResponse(status="success", data=data, meta=meta)

@router.get(
    "/inbound/details",
    response_model=StandardResponse[list[ShipmentDetailItem]],
    summary="Search & Paginate through active waybills"
)
async def get_inbound_details(
    request: Request,
    search: str | None = Query(default=None, description="Search by waybillno or network/station"),
    status: str | None = Query(default=None, description="Filter by status_order e.g. 'Đang trên bãi'"),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(default=50, ge=1, le=500, description="Records per page")
):
    start_t = time.perf_counter()
    items, total_records = DashboardService.search_shipments(
        search=search, status_filter=status, page=page, page_size=size
    )
    duration_ms = round((time.perf_counter() - start_t) * 1000, 2)
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    total_pages = ceil(total_records / size) if size > 0 else 0

    meta = PaginationMeta(
        trace_id=trace_id,
        execution_ms=duration_ms,
        current_page=page,
        page_size=size,
        total_records=total_records,
        total_pages=total_pages
    )
    return StandardResponse(status="success", data=items, meta=meta)
