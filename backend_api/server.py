"""
Main Entry Point for FastAPI Backend Service (Enterprise Architecture v5)
Orchestrates Uvicorn ASGI lifecycle, connection pool init, trace ID middlewares, and routers.
"""
import time
import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

try:
    from backend_api.config import settings
except ImportError:
    from config import settings
from db.connection import init_db_pool, close_db_pool
from routers.dashboard_router import router as dashboard_router
from routers.admin_router import router as admin_router
from schemas.common import ErrorResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("api.server")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler guaranteeing clean pool setup on startup & shutdown."""
    logger.info(f"Booting {settings.APP_NAME} v{settings.APP_VERSION} ({settings.ENVIRONMENT})...")
    init_db_pool()
    yield
    logger.info("Shutting down service and releasing database connections...")
    close_db_pool()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise Low-Latency API Service for Sortation Center Dashboard (P50 < 50ms)",
    lifespan=lifespan
)

# CORS Middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_trace_and_timing_middleware(request: Request, call_next):
    """Injects unique Trace ID and calculates precise execution_ms for SLA monitoring."""
    trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
    request.state.trace_id = trace_id
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Execution-Time-Ms"] = str(duration_ms)
        return response
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(f"[{trace_id}] Uncaught exception on {request.method} {request.url.path}: {exc}")
        err_payload = ErrorResponse(
            status="error",
            error_code="ERR_INTERNAL_SERVER",
            message=str(exc)
        )
        return JSONResponse(
            status_code=500,
            content=err_payload.model_dump(),
            headers={"X-Trace-Id": trace_id, "X-Execution-Time-Ms": str(duration_ms)}
        )

# Register routers under /api/v1 prefix
app.include_router(dashboard_router, prefix=settings.API_PREFIX)
app.include_router(admin_router, prefix=settings.API_PREFIX)

@app.get("/", summary="Health check root redirect")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "active",
        "docs_url": "/docs",
        "health_check": f"{settings.API_PREFIX}/admin/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=(settings.ENVIRONMENT == "development")
    )
