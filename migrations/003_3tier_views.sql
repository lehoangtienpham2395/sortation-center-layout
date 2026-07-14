-- ==============================================================================
-- MIGRATION 003: 3-TIER VIEWS (STANDARD SQL VIEWS & MATERIALIZED VIEWS)
-- Standard SQL Views (Tier 2) for active filters
-- Materialized Views (Tier 3) with CONCURRENTLY refresh support for Heavy KPIs
-- ==============================================================================

-- TIER 2: STANDARD SQL VIEWS (Realtime non-blocking virtual views)
CREATE OR REPLACE VIEW vw_shipments_active AS
SELECT * FROM shipments WHERE is_active = 1;

CREATE OR REPLACE VIEW vw_chute_occupancy AS
SELECT 
    COALESCE(nm.mapped_area_id, 'UNKNOWN') AS area_id,
    COALESCE(cm.chute_name, s.picknetworkname, 'Bưu cục khác') AS chute_name,
    COALESCE(cm.zone_id, 0) AS zone_id,
    COUNT(s.waybillno) AS current_volume,
    ROUND(SUM(s.weight)::numeric, 2) AS current_weight_kg
FROM shipments s
LEFT JOIN network_master nm ON s.picknetworkname = nm.network_name
LEFT JOIN chutes_master cm ON nm.mapped_area_id = cm.area_id
WHERE s.is_active = 1
GROUP BY COALESCE(nm.mapped_area_id, 'UNKNOWN'), COALESCE(cm.chute_name, s.picknetworkname, 'Bưu cục khác'), COALESCE(cm.zone_id, 0);

-- TIER 3: MATERIALIZED VIEWS (For heavy analytical aggregation < 15ms query)

-- 1. MV tổng hợp cho Dashboard Inbound (Gom nhóm theo Bưu Cục & Máng Trượt)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dashboard_inbound AS
SELECT 
    COALESCE(nm.mapped_area_id, 'UNKNOWN') AS area_id,
    COALESCE(cm.chute_name, s.picknetworkname, 'Bưu cục khác') AS chute_name,
    COALESCE(cm.zone_id, 0) AS zone_id,
    COUNT(s.waybillno) AS total_volume,
    ROUND(SUM(s.weight)::numeric, 2) AS total_weight_kg,
    ROUND(AVG(NULLIF(s.weight, 0))::numeric, 2) AS avg_weight_kg,
    SUM(CASE WHEN s.is_backlog = 1 THEN 1 ELSE 0 END) AS backlog_count,
    MAX(s.last_updated) AS last_scanned_at
FROM shipments s
LEFT JOIN network_master nm ON s.picknetworkname = nm.network_name
LEFT JOIN chutes_master cm ON nm.mapped_area_id = cm.area_id
WHERE s.is_active = 1 AND s.inbound_scandate IS NOT NULL
GROUP BY COALESCE(nm.mapped_area_id, 'UNKNOWN'), COALESCE(cm.chute_name, s.picknetworkname, 'Bưu cục khác'), COALESCE(cm.zone_id, 0);

-- Unique index bắt buộc để hỗ trợ REFRESH MATERIALIZED VIEW CONCURRENTLY (Không khóa bảng)
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_dashboard_inbound_unique ON mv_dashboard_inbound (area_id, chute_name);

-- 2. MV tổng hợp xu hướng theo khung giờ (Hourly Trend cho Biểu đồ Inbound)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_trend_inbound_hourly AS
SELECT 
    TO_CHAR(NULLIF(TRIM(s.inbound_scandate::text), '')::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:00') AS hour_bucket,
    TO_CHAR(NULLIF(TRIM(s.inbound_scandate::text), '')::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'HH24:00') AS time_label,
    COUNT(*) AS hourly_volume,
    ROUND(SUM(s.weight)::numeric, 2) AS hourly_weight_kg
FROM shipments s
WHERE s.is_active = 1 AND NULLIF(TRIM(s.inbound_scandate::text), '') IS NOT NULL AND s.inbound_scandate::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
GROUP BY TO_CHAR(NULLIF(TRIM(s.inbound_scandate::text), '')::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:00'), TO_CHAR(NULLIF(TRIM(s.inbound_scandate::text), '')::timestamptz AT TIME ZONE 'Asia/Ho_Chi_Minh', 'HH24:00')
ORDER BY hour_bucket DESC
LIMIT 48;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_trend_inbound_unique ON mv_trend_inbound_hourly (hour_bucket);

-- 3. MV tổng hợp cho Dashboard Outbound
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dashboard_outbound AS
SELECT 
    COALESCE(s.next_station, 'Trạm khác') AS station_name,
    COUNT(s.waybillno) AS total_volume,
    ROUND(SUM(s.weight)::numeric, 2) AS total_weight_kg,
    ROUND(AVG(NULLIF(s.weight, 0))::numeric, 2) AS avg_weight_kg,
    MAX(s.last_updated) AS last_scanned_at
FROM shipments s
WHERE s.is_active = 1 AND s.outbound_scandate IS NOT NULL
GROUP BY COALESCE(s.next_station, 'Trạm khác');

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_dashboard_outbound_unique ON mv_dashboard_outbound (station_name);
