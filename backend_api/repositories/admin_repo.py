"""
Repository Layer for Admin & Monitoring API (Enterprise Architecture v5)
Executes administrative queries for health diagnostics, ETL audit logs, and cold storage archival.
"""
import logging
from db.connection import get_db_cursor
from config import settings

logger = logging.getLogger("api.repo.admin")

class AdminRepository:
    """Provides system monitoring and database maintenance operations."""

    @staticmethod
    def get_database_storage_size() -> tuple[int, str]:
        """Returns database size in bytes and human readable format."""
        query = "SELECT pg_database_size(current_database()) AS size_bytes, pg_size_pretty(pg_database_size(current_database())) AS size_human;"
        try:
            with get_db_cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
                return (row[0], row[1]) if row else (0, "0 MB")
        except Exception as e:
            logger.error(f"Error checking DB size: {e}")
            return (0, "N/A")

    @staticmethod
    def get_active_shipments_count() -> int:
        """Returns count of active records inside the HUB."""
        query = "SELECT COUNT(*) FROM shipments WHERE is_active = 1;"
        try:
            with get_db_cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"Error counting active shipments: {e}")
            return 0

    @staticmethod
    def get_latest_successful_etl_time() -> str | None:
        """Returns timestamp of most recent SUCCESS ETL sync job."""
        query = """
            SELECT TO_CHAR(end_time::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI:SS')
            FROM etl_job_history
            WHERE status = 'SUCCESS'
            ORDER BY end_time DESC
            LIMIT 1;
        """
        try:
            with get_db_cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    @staticmethod
    def fetch_etl_history_list(limit: int = 20) -> list[dict]:
        """Fetches recent ETL synchronization job histories."""
        query = """
            SELECT 
                job_id,
                TO_CHAR(start_time::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI:SS') AS start_time,
                TO_CHAR(end_time::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI:SS') AS end_time,
                duration_sec, status, records_processed, error_message, triggered_by
            FROM etl_job_history
            ORDER BY start_time DESC
            LIMIT %s;
        """
        with get_db_cursor() as cur:
            cur.execute(query, [limit])
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in rows]

    @staticmethod
    def archive_inactive_shipments_older_than(days: int = 60) -> int:
        """Deletes or archives shipments where is_active = 0 and older than retention window."""
        query = """
            DELETE FROM shipments 
            WHERE is_active = 0 
              AND last_updated < NOW() - INTERVAL '%s days'
            RETURNING waybillno;
        """
        with get_db_cursor() as cur:
            cur.execute(query, [days])
            deleted_rows = cur.fetchall()
            return len(deleted_rows)
