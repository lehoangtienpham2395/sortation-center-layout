"""
Service Layer for Admin & Monitoring API (Enterprise Architecture v5)
Orchestrates system health checks, connection pool verification, and data archival jobs.
"""
import time
from repositories.admin_repo import AdminRepository
from db.connection import get_pool_diagnostics
from schemas.admin import SystemHealthData, ConnectionPoolStatus, EtlHistoryItem, ArchiveCleanupResult

class AdminService:
    """Manages administrative monitoring and system operations."""

    @staticmethod
    def get_system_health() -> SystemHealthData:
        """Retrieves comprehensive system diagnostics and pool telemetry."""
        pool_diag = get_pool_diagnostics()
        pool_status_obj = ConnectionPoolStatus(**pool_diag)

        db_bytes, db_human = AdminRepository.get_database_storage_size()
        active_count = AdminRepository.get_active_shipments_count()
        last_etl = AdminRepository.get_latest_successful_etl_time()

        overall_status = "OK"
        if pool_diag["status"] != "HEALTHY" or db_bytes > 450_000_000:  # > 450MB warning on Neon Free Tier
            overall_status = "WARNING"

        return SystemHealthData(
            system_status=overall_status,
            database_connection="CONNECTED",
            database_size_bytes=db_bytes,
            database_size_human=db_human,
            active_shipments_count=active_count,
            last_successful_etl_time=last_etl,
            connection_pool=pool_status_obj
        )

    @staticmethod
    def get_etl_job_histories(limit: int = 20) -> list[EtlHistoryItem]:
        """Retrieves audit logs of recent ETL synchronization jobs."""
        records = AdminRepository.fetch_etl_history_list(limit=limit)
        return [
            EtlHistoryItem(
                job_id=row["job_id"],
                start_time=row["start_time"],
                end_time=row.get("end_time"),
                duration_sec=row.get("duration_sec"),
                status=row["status"],
                records_processed=row.get("records_processed", 0),
                error_message=row.get("error_message"),
                triggered_by=row.get("triggered_by", "CRON")
            )
            for row in records
        ]

    @staticmethod
    def trigger_archive_cleanup(days: int = 60) -> ArchiveCleanupResult:
        """Executes cleanup/archival of old inactive shipment records."""
        start_t = time.perf_counter()
        deleted = AdminRepository.archive_inactive_shipments_older_than(days=days)
        duration = time.perf_counter() - start_t

        return ArchiveCleanupResult(
            action=f"CLEANUP_INACTIVE_OLDER_THAN_{days}_DAYS",
            records_deleted=deleted,
            records_archived=deleted,
            execution_duration_sec=round(duration, 3)
        )
