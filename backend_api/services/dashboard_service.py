"""
Service Layer for Dashboard API (Enterprise Architecture v5)
Encapsulates business mapping, data validation, and DTO construction.
Ensures zero SQL in Routers while transforming repository dictionaries to Pydantic objects.
"""
from decimal import Decimal
from repositories.dashboard_repo import DashboardRepository
from schemas.dashboard import (
    ChuteVolumeItem, HourlyTrendItem, InboundDashboardData,
    OutboundStationItem, OutboundDashboardData, ShipmentDetailItem
)

class DashboardService:
    """Orchestrates dashboard data retrieval and DTO assembly."""

    @staticmethod
    def get_inbound_dashboard() -> InboundDashboardData:
        """Retrieves and packages aggregated data for the Inbound Dashboard."""
        summary = DashboardRepository.fetch_inbound_summary_totals()
        chutes_raw = DashboardRepository.fetch_inbound_chutes_summary()
        trend_raw = DashboardRepository.fetch_inbound_hourly_trend()

        chutes_list = [
            ChuteVolumeItem(
                area_id=row["area_id"],
                chute_name=row["chute_name"],
                zone_id=row["zone_id"],
                total_volume=row["total_volume"],
                total_weight_kg=Decimal(str(row["total_weight_kg"])),
                avg_weight_kg=Decimal(str(row["avg_weight_kg"])),
                backlog_count=row["backlog_count"],
                last_scanned_at=row["last_scanned_at"]
            )
            for row in chutes_raw
        ]

        trend_list = [
            HourlyTrendItem(
                hour_bucket=row["hour_bucket"],
                time_label=row["time_label"],
                hourly_volume=row["hourly_volume"],
                hourly_weight_kg=Decimal(str(row["hourly_weight_kg"]))
            )
            for row in trend_raw
        ]

        return InboundDashboardData(
            summary_volume=summary.get("summary_volume", 0),
            summary_weight_kg=Decimal(str(summary.get("summary_weight_kg", "0.00"))),
            summary_avg_weight_kg=Decimal(str(summary.get("summary_avg_weight_kg", "0.00"))),
            summary_backlog_volume=summary.get("summary_backlog_volume", 0),
            chutes_table=chutes_list,
            hourly_trend=trend_list,
            last_sync_timestamp=summary.get("last_sync_timestamp")
        )

    @staticmethod
    def get_outbound_dashboard() -> OutboundDashboardData:
        """Retrieves and packages aggregated data for the Outbound Dashboard."""
        summary = DashboardRepository.fetch_outbound_summary_totals()
        stations_raw = DashboardRepository.fetch_outbound_stations_summary()

        stations_list = [
            OutboundStationItem(
                station_name=row["station_name"],
                total_volume=row["total_volume"],
                total_weight_kg=Decimal(str(row["total_weight_kg"])),
                avg_weight_kg=Decimal(str(row["avg_weight_kg"])),
                last_scanned_at=row["last_scanned_at"]
            )
            for row in stations_raw
        ]

        return OutboundDashboardData(
            summary_volume=summary.get("summary_volume", 0),
            summary_weight_kg=Decimal(str(summary.get("summary_weight_kg", "0.00"))),
            stations_table=stations_list,
            last_sync_timestamp=summary.get("last_sync_timestamp")
        )

    @staticmethod
    def search_shipments(
        search: str | None = None,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 50
    ) -> tuple[list[ShipmentDetailItem], int]:
        """Retrieves paginated detail list of active shipments."""
        records_raw, total_count = DashboardRepository.fetch_shipments_paginated(
            search=search, status_filter=status_filter, page=page, page_size=page_size
        )

        items = [
            ShipmentDetailItem(
                waybillno=row["waybillno"],
                data_source=row["data_source"],
                weight=Decimal(str(row["weight"] or "0.00")),
                picknetworkname=row.get("picknetworkname"),
                dispatch_plan=row.get("dispatch_plan"),
                pickup_time=row.get("pickup_time"),
                pickup_label=row.get("pickup_label"),
                pickup_ontime=row.get("pickup_ontime"),
                dispatchnetworktime=row.get("dispatchnetworktime"),
                next_station=row.get("next_station"),
                tuyen=row.get("tuyen"),
                rank=row.get("rank"),
                inbound_network=row.get("inbound_network"),
                inbound_scandate=row.get("inbound_scandate"),
                outbound_scandate=row.get("outbound_scandate"),
                arrival_time=row.get("arrival_time"),
                dispatch_actual=row.get("dispatch_actual"),
                status_order=row["status_order"],
                is_backlog=row.get("is_backlog", 0),
                is_active=row.get("is_active", 1),
                last_updated=row.get("last_updated")
            )
            for row in records_raw
        ]

        return items, total_count
