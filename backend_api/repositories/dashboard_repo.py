"""
Repository Layer for Dashboard API (Enterprise Architecture v5)
Sole layer authorized to execute raw SQL queries for Dashboard data.
Guarantees P50 < 50ms latency by querying Tier 3 Materialized Views.
"""
import logging
from decimal import Decimal
from db.connection import get_db_cursor

logger = logging.getLogger("api.repo.dashboard")

class DashboardRepository:
    """Provides fast read-only access to pre-aggregated materialized views & shipments."""

    @staticmethod
    def fetch_inbound_chutes_summary() -> list[dict]:
        """Queries mv_dashboard_inbound for Chute/Network level KPIs."""
        query = """
            SELECT 
                area_id, chute_name, zone_id, total_volume, 
                total_weight_kg, avg_weight_kg, backlog_count, 
                TO_CHAR(last_scanned_at::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI:SS') AS last_scanned_at
            FROM mv_dashboard_inbound
            ORDER BY total_volume DESC;
        """
        with get_db_cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in rows]

    @staticmethod
    def fetch_inbound_hourly_trend() -> list[dict]:
        """Queries mv_trend_inbound_hourly for hourly scan progression."""
        query = """
            SELECT 
                hour_bucket, time_label, hourly_volume, hourly_weight_kg
            FROM mv_trend_inbound_hourly
            ORDER BY hour_bucket ASC;
        """
        with get_db_cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in rows]

    @staticmethod
    def fetch_inbound_summary_totals() -> dict:
        """Calculates exact aggregate totals directly from shipments where is_active=1 and inbound_scandate is not null."""
        query = """
            SELECT 
                COUNT(*) AS summary_volume,
                COALESCE(ROUND(SUM(weight)::numeric, 2), 0.00) AS summary_weight_kg,
                COALESCE(ROUND(AVG(NULLIF(weight, 0))::numeric, 2), 0.00) AS summary_avg_weight_kg,
                SUM(CASE WHEN is_backlog = 1 THEN 1 ELSE 0 END) AS summary_backlog_volume,
                TO_CHAR(MAX(last_updated)::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI:SS') AS last_sync_timestamp
            FROM shipments
            WHERE is_active = 1 AND inbound_scandate IS NOT NULL;
        """
        with get_db_cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()
            if not row or row[0] is None:
                return {
                    "summary_volume": 0,
                    "summary_weight_kg": Decimal("0.00"),
                    "summary_avg_weight_kg": Decimal("0.00"),
                    "summary_backlog_volume": 0,
                    "last_sync_timestamp": None
                }
            columns = [desc[0] for desc in cur.description]
            return dict(zip(columns, row))

    @staticmethod
    def fetch_outbound_stations_summary() -> list[dict]:
        """Queries mv_dashboard_outbound for next_station volume breakdown."""
        query = """
            SELECT 
                station_name, total_volume, total_weight_kg, avg_weight_kg,
                TO_CHAR(last_scanned_at::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI:SS') AS last_scanned_at
            FROM mv_dashboard_outbound
            ORDER BY total_volume DESC;
        """
        with get_db_cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in rows]

    @staticmethod
    def fetch_outbound_summary_totals() -> dict:
        """Calculates outbound aggregate totals."""
        query = """
            SELECT 
                COUNT(*) AS summary_volume,
                COALESCE(ROUND(SUM(weight)::numeric, 2), 0.00) AS summary_weight_kg,
                TO_CHAR(MAX(last_updated)::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI:SS') AS last_sync_timestamp
            FROM shipments
            WHERE is_active = 1 AND outbound_scandate IS NOT NULL;
        """
        with get_db_cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()
            columns = [desc[0] for desc in cur.description]
            return dict(zip(columns, row)) if row else {"summary_volume": 0, "summary_weight_kg": Decimal("0.00")}

    @staticmethod
    def fetch_shipments_paginated(
        search: str | None = None,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 50
    ) -> tuple[list[dict], int]:
        """Performs paginated search on shipments table."""
        offset = (page - 1) * page_size
        where_clauses = ["is_active = 1"]
        params = []

        if search and search.strip():
            where_clauses.append("(waybillno ILIKE %s OR picknetworkname ILIKE %s OR next_station ILIKE %s)")
            kw = f"%{search.strip()}%"
            params.extend([kw, kw, kw])
        
        if status_filter and status_filter.strip():
            where_clauses.append("status_order = %s")
            params.append(status_filter.strip())

        where_sql = " AND ".join(where_clauses)

        count_query = f"SELECT COUNT(*) FROM shipments WHERE {where_sql};"
        list_query = f"""
            SELECT 
                waybillno, data_source, weight, picknetworkname, dispatch_plan,
                TO_CHAR(pickup_time::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI:SS') AS pickup_time,
                pickup_label, pickup_ontime,
                TO_CHAR(dispatchnetworktime::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI:SS') AS dispatchnetworktime,
                next_station, tuyen, rank, inbound_network,
                TO_CHAR(inbound_scandate::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI:SS') AS inbound_scandate,
                TO_CHAR(outbound_scandate::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI:SS') AS outbound_scandate,
                TO_CHAR(arrival_time::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI:SS') AS arrival_time,
                dispatch_actual, status_order, is_backlog, is_active,
                TO_CHAR(last_updated::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI:SS') AS last_updated
            FROM shipments
            WHERE {where_sql}
            ORDER BY last_updated DESC
            LIMIT %s OFFSET %s;
        """

        with get_db_cursor() as cur:
            cur.execute(count_query, params)
            total_records = cur.fetchone()[0]

            list_params = params + [page_size, offset]
            cur.execute(list_query, list_params)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            records = [dict(zip(columns, row)) for row in rows]

            return records, total_records
