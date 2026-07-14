"""
Connection Pooling and Database Utility Module (Enterprise Architecture v5)
Provides ThreadedConnectionPool management, context-managed connection checkout,
and migration execution utilities for PostgreSQL (Neon Cloud / Local).
"""
import os
import sys
import logging
from contextlib import contextmanager
import psycopg2
from psycopg2 import pool, extras

logger = logging.getLogger("db.pool")

# Default database parameters (can be overridden by environment variables)
DB_HOST = os.environ.get("PGHOST", "localhost")
DB_PORT = int(os.environ.get("PGPORT", 5433))
DB_USER = os.environ.get("PGUSER", "postgres")
DB_PASSWORD = os.environ.get("PGPASSWORD", "postgres")
DB_NAME = os.environ.get("PGDATABASE", "postgres")
DATABASE_URL = os.environ.get("DATABASE_URL")

_CONNECTION_POOL = None

NEON_URL = "postgresql://neondb_owner:npg_i0dyTk6oeEmD@ep-dawn-poetry-atfofe2l-pooler.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

def get_pool():
    """Returns a singleton ThreadedConnectionPool instance."""
    global _CONNECTION_POOL
    if _CONNECTION_POOL is None or _CONNECTION_POOL.closed:
        try:
            target_url = DATABASE_URL
            if os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("USE_NEON") == "true":
                target_url = target_url or NEON_URL

            if target_url:
                logger.info("Initializing ThreadedConnectionPool with Cloud URL (Neon Pooler)...")
                _CONNECTION_POOL = psycopg2.pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=25,
                    dsn=target_url,
                    connect_timeout=15
                )
            else:
                try:
                    logger.info(f"Initializing ThreadedConnectionPool with Local DB {DB_HOST}:{DB_PORT}/{DB_NAME}...")
                    _CONNECTION_POOL = psycopg2.pool.ThreadedConnectionPool(
                        minconn=2,
                        maxconn=25,
                        host=DB_HOST,
                        port=DB_PORT,
                        user=DB_USER,
                        password=DB_PASSWORD,
                        dbname=DB_NAME,
                        connect_timeout=3
                    )
                except Exception as local_err:
                    logger.warning(f"Local DB {DB_HOST}:{DB_PORT} unreachable ({local_err}). Fallback to Neon Cloud Pooler...")
                    _CONNECTION_POOL = psycopg2.pool.ThreadedConnectionPool(
                        minconn=2,
                        maxconn=25,
                        dsn=NEON_URL,
                        connect_timeout=15
                    )
            logger.info("Database connection pool successfully initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL Connection Pool: {e}")
            raise
    return _CONNECTION_POOL

class PooledConnectionProxy:
    """Proxy around pooled connection so conn.close() returns it to the pool cleanly."""
    def __init__(self, conn, pool_instance):
        self._conn = conn
        self._pool_instance = pool_instance
        self._closed = False

    def close(self):
        if not self._closed and self._conn is not None:
            self._pool_instance.putconn(self._conn)
            self._closed = True

    def __getattr__(self, name):
        return getattr(self._conn, name)

def get_proxy_connection():
    """Returns a pooled connection proxy whose close() method returns conn to pool."""
    pool_instance = get_pool()
    conn = pool_instance.getconn()
    return PooledConnectionProxy(conn, pool_instance)

@contextmanager
def get_db_connection():
    """Context manager for safely borrowing and returning a pooled connection."""
    pool_instance = get_pool()
    conn = None
    try:
        conn = pool_instance.getconn()
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error during pooled connection execution: {e}")
        raise
    finally:
        if conn:
            pool_instance.putconn(conn)

def close_pool():
    """Closes all connections in the pool."""
    global _CONNECTION_POOL
    if _CONNECTION_POOL and not _CONNECTION_POOL.closed:
        _CONNECTION_POOL.closeall()
        logger.info("Database connection pool closed.")

def run_sql_file(conn, sql_path):
    """Executes a SQL script file within the given connection."""
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    with conn.cursor() as cur:
        cur.execute(sql_content)
    conn.commit()
    logger.info(f"Successfully executed migration script: {os.path.basename(sql_path)}")

def execute_all_migrations(migrations_dir=None):
    """Executes all migration scripts in numerical order."""
    if migrations_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        migrations_dir = os.path.join(base_dir, "migrations")
    
    if not os.path.exists(migrations_dir):
        raise FileNotFoundError(f"Migrations directory not found: {migrations_dir}")
        
    sql_files = sorted([f for f in os.listdir(migrations_dir) if f.endswith(".sql")])
    logger.info(f"Found {len(sql_files)} migration files in {migrations_dir}.")
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for col in ['inbound_scandate', 'outbound_scandate', 'pickup_time', 'dispatchnetworktime', 'arrival_time', 'time_ref']:
                try:
                    cur.execute(f"UPDATE shipments SET {col} = NULL WHERE {col}::text = 'Backlog' OR {col}::text = '' OR NOT ({col}::text ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}');")
                except Exception:
                    conn.rollback()
            conn.commit()
        for sql_file in sql_files:
            file_path = os.path.join(migrations_dir, sql_file)
            run_sql_file(conn, file_path)
    logger.info("All database migrations completed successfully.")

def batch_upsert_shipments(records, batch_size=2000):
    """
    Performs high-throughput UPSERT into shipments table using execute_values.
    Expects tuples formatted according to shipments table schema (21 or 22 columns).
    """
    if not records:
        return 0
        
    has_last_updated = (len(records[0]) == 22)
    cols = """
        waybillno, data_source, weight, picknetworkname, dispatch_plan, pickup_time, pickup_label, 
        pickup_ontime, dispatchnetworktime, next_station, tuyen, rank, inbound_network, 
        inbound_scandate, outbound_scandate, arrival_time, dispatch_actual, status_order, 
        time_ref, is_backlog, is_active
    """
    if has_last_updated:
        cols += ", last_updated"

    query = f"""
        INSERT INTO shipments ({cols}) VALUES %s
        ON CONFLICT (waybillno) DO UPDATE SET
            weight = CASE WHEN EXCLUDED.weight > 0 THEN EXCLUDED.weight ELSE shipments.weight END,
            inbound_scandate = COALESCE(EXCLUDED.inbound_scandate, shipments.inbound_scandate),
            outbound_scandate = COALESCE(EXCLUDED.outbound_scandate, shipments.outbound_scandate),
            arrival_time = COALESCE(EXCLUDED.arrival_time, shipments.arrival_time),
            pickup_time = COALESCE(EXCLUDED.pickup_time, shipments.pickup_time),
            dispatchnetworktime = COALESCE(EXCLUDED.dispatchnetworktime, shipments.dispatchnetworktime),
            status_order = EXCLUDED.status_order,
            is_active = EXCLUDED.is_active,
            is_backlog = EXCLUDED.is_backlog,
            data_source = EXCLUDED.data_source,
            picknetworkname = COALESCE(NULLIF(EXCLUDED.picknetworkname, ''), shipments.picknetworkname),
            last_updated = NOW();
    """
    
    import re
    cleaned_records = []
    ts_indices = {5, 8, 13, 14, 15, 18, 21}
    for row in records:
        r_list = list(row)
        for idx in ts_indices:
            if idx < len(r_list) and isinstance(r_list[idx], str):
                s = r_list[idx].strip()
                if not s or not re.match(r'^\d{4}-\d{2}-\d{2}', s):
                    r_list[idx] = None
                else:
                    r_list[idx] = s
        cleaned_records.append(tuple(r_list))
    records = cleaned_records

    processed = 0
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                extras.execute_values(cur, query, batch, page_size=batch_size)
                processed += len(batch)
        conn.commit()
    logger.info(f"UPSERT completed: {processed} shipment records processed.")
    return processed

def refresh_materialized_views():
    """Safely refreshes materialized views using CONCURRENTLY without locking."""
    views = ["mv_dashboard_inbound", "mv_trend_inbound_hourly", "mv_dashboard_outbound"]
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for view_name in views:
                try:
                    cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name};")
                    logger.info(f"Refreshed materialized view: {view_name}")
                except Exception as e:
                    logger.warning(f"Could not refresh {view_name} concurrently (might be empty or missing unique index): {e}")
                    conn.rollback()
                    try:
                        cur.execute(f"REFRESH MATERIALIZED VIEW {view_name};")
                        conn.commit()
                        logger.info(f"Refreshed materialized view standard mode: {view_name}")
                    except Exception as e2:
                        logger.error(f"Failed to refresh {view_name}: {e2}")
                        conn.rollback()
        conn.commit()
