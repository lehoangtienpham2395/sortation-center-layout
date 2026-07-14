"""
Pydantic v2 Schemas for Dashboard API Endpoints (Enterprise Architecture v5)
Defines response payloads for Inbound, Outbound, and Detail views without UI business logic.
"""
from pydantic import BaseModel, Field
from decimal import Decimal

class ChuteVolumeItem(BaseModel):
    """Represents pre-aggregated shipment volume and weight per chute/station."""
    area_id: str = Field(..., description="Chute or Area ID e.g. C01")
    chute_name: str = Field(..., description="Full network/chute name")
    zone_id: int = Field(default=0, description="Sortation zone ID")
    total_volume: int = Field(default=0, ge=0, description="Count of active shipments")
    total_weight_kg: Decimal = Field(default=Decimal("0.00"), description="Total weight exactly to 2 decimal places")
    avg_weight_kg: Decimal = Field(default=Decimal("0.00"), description="Average weight per package")
    backlog_count: int = Field(default=0, ge=0, description="Number of packages backlog > 24h")
    last_scanned_at: str | None = Field(default=None, description="Latest scan timestamp")

class HourlyTrendItem(BaseModel):
    """Represents hourly distribution bucket for volume and weight trend charts."""
    hour_bucket: str = Field(..., description="YYYY-MM-DD HH:00 time bucket")
    time_label: str = Field(..., description="Formatted hour string e.g. 14:00")
    hourly_volume: int = Field(default=0, ge=0)
    hourly_weight_kg: Decimal = Field(default=Decimal("0.00"))

class InboundDashboardData(BaseModel):
    """Aggregate payload returned by GET /api/v1/dashboard/inbound"""
    summary_volume: int = Field(default=0, description="Total active volume currently inside HUB")
    summary_weight_kg: Decimal = Field(default=Decimal("0.00"), description="Total active weight inside HUB")
    summary_avg_weight_kg: Decimal = Field(default=Decimal("0.00"))
    summary_backlog_volume: int = Field(default=0)
    chutes_table: list[ChuteVolumeItem] = Field(default_factory=list)
    hourly_trend: list[HourlyTrendItem] = Field(default_factory=list)
    last_sync_timestamp: str | None = Field(default=None)

class OutboundStationItem(BaseModel):
    """Volume and weight broken down by next outbound destination station."""
    station_name: str = Field(...)
    total_volume: int = Field(default=0, ge=0)
    total_weight_kg: Decimal = Field(default=Decimal("0.00"))
    avg_weight_kg: Decimal = Field(default=Decimal("0.00"))
    last_scanned_at: str | None = Field(default=None)

class OutboundDashboardData(BaseModel):
    """Aggregate payload returned by GET /api/v1/dashboard/outbound"""
    summary_volume: int = Field(default=0)
    summary_weight_kg: Decimal = Field(default=Decimal("0.00"))
    stations_table: list[OutboundStationItem] = Field(default_factory=list)
    last_sync_timestamp: str | None = Field(default=None)

class ShipmentDetailItem(BaseModel):
    """Detailed record representation for waybill search & paginated tables."""
    waybillno: str
    data_source: str
    weight: Decimal
    picknetworkname: str | None = None
    dispatch_plan: str | None = None
    pickup_time: str | None = None
    pickup_label: str | None = None
    pickup_ontime: str | None = None
    dispatchnetworktime: str | None = None
    next_station: str | None = None
    tuyen: str | None = None
    rank: str | None = None
    inbound_network: str | None = None
    inbound_scandate: str | None = None
    outbound_scandate: str | None = None
    arrival_time: str | None = None
    dispatch_actual: str | None = None
    status_order: str
    is_backlog: int = 0
    is_active: int = 1
    last_updated: str | None = None
