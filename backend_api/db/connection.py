"""
FastAPI Database Connection Manager (Enterprise Architecture v5)
Manages the ThreadedConnectionPool lifecycle across Uvicorn startup/shutdown events.
Ensures connection borrow/return safety and zero pool leakage.
"""
import logging
from contextlib import contextmanager
import psycopg2
from psycopg2 import pool
from config import settings

logger = logging.getLogger("api.db")

_FASTAPI_POOL: pool.ThreadedConnectionPool | None = None

def init_db_pool():
    """Initializes the ThreadedConnectionPool on FastAPI lifespan startup."""
    global _FASTAPI_POOL
    if _FASTAPI_POOL is None or _FASTAPI_POOL.closed:
        try:
            target_url = settings.DATABASE_URL
            # If no DATABASE_URL or if local unreachable, fallback or use target
            if target_url:
                logger.info("Connecting FastAPI Pool to Cloud DATABASE_URL...")
                _FASTAPI_POOL = psycopg2.pool.ThreadedConnectionPool(
                    minconn=settings.DB_POOL_MIN_CONN,
                    maxconn=settings.DB_POOL_MAX_CONN,
                    dsn=target_url,
                    connect_timeout=settings.DB_CONNECT_TIMEOUT
                )
            else:
                try:
                    logger.info(f"Connecting FastAPI Pool to Local DB {settings.PGHOST}:{settings.PGPORT}/{settings.PGDATABASE}...")
                    _FASTAPI_POOL = psycopg2.pool.ThreadedConnectionPool(
                        minconn=settings.DB_POOL_MIN_CONN,
                        maxconn=settings.DB_POOL_MAX_CONN,
                        host=settings.PGHOST,
                        port=settings.PGPORT,
                        user=settings.PGUSER,
                        password=settings.PGPASSWORD,
                        dbname=settings.PGDATABASE,
                        connect_timeout=3
                    )
                except Exception as local_err:
                    logger.warning(f"Local DB unreachable ({local_err}). Fallback to Neon Pooler...")
                    _FASTAPI_POOL = psycopg2.pool.ThreadedConnectionPool(
                        minconn=settings.DB_POOL_MIN_CONN,
                        maxconn=settings.DB_POOL_MAX_CONN,
                        dsn=settings.NEON_POOLER_URL,
                        connect_timeout=settings.DB_CONNECT_TIMEOUT
                    )
            logger.info("FastAPI ThreadedConnectionPool successfully initialized.")
        except Exception as e:
            logger.error(f"Critical error initializing FastAPI database pool: {e}")
            raise

def close_db_pool():
    """Closes all connections in the pool on FastAPI shutdown."""
    global _FASTAPI_POOL
    if _FASTAPI_POOL and not _FASTAPI_POOL.closed:
        _FASTAPI_POOL.closeall()
        logger.info("FastAPI ThreadedConnectionPool closed cleanly.")

def get_pool() -> pool.ThreadedConnectionPool:
    """Returns the singleton FastAPI pool instance."""
    if _FASTAPI_POOL is None or _FASTAPI_POOL.closed:
        init_db_pool()
    return _FASTAPI_POOL

@contextmanager
def get_db_cursor():
    """Context manager yielding a database cursor from a pooled connection."""
    pool_instance = get_pool()
    conn = None
    try:
        conn = pool_instance.getconn()
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database query execution error: {e}")
        raise
    finally:
        if conn:
            pool_instance.putconn(conn)

def get_pool_diagnostics() -> dict:
    """Returns real-time connection pool health metrics for admin diagnostics."""
    pool_instance = get_pool()
    # Check private attributes of ThreadedConnectionPool safely
    used_conns = len(getattr(pool_instance, '_used', {}))
    pool_size = len(getattr(pool_instance, '_pool', [])) + used_conns
    max_conn = getattr(pool_instance, 'maxconn', settings.DB_POOL_MAX_CONN)
    min_conn = getattr(pool_instance, 'minconn', settings.DB_POOL_MIN_CONN)
    avail_conns = max_conn - used_conns
    usage_pct = round((used_conns / max_conn) * 100, 1) if max_conn > 0 else 0.0

    return {
        "status": "HEALTHY" if usage_pct < 85.0 else "WARNING_POOL_HIGH",
        "minconn": min_conn,
        "maxconn": max_conn,
        "active_used_connections": used_conns,
        "available_connections": avail_conns,
        "pool_usage_percent": usage_pct
    }
