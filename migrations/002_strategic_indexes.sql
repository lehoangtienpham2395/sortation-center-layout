-- ==============================================================================
-- MIGRATION 002: STRATEGIC B-TREE INDEXES FOR P50 < 50ms QUERY PERFORMANCE
-- Partial B-Tree indexes targeting active records in the HUB
-- ==============================================================================

-- 1. Index tối ưu lọc các đơn đang active trong HUB và theo trạng thái
CREATE INDEX IF NOT EXISTS idx_shipments_active_status 
    ON shipments (is_active, status_order) 
    WHERE is_active = 1;

-- 2. Index tối ưu truy vấn mốc thời gian Inbound cho Dashboard Inbound & Hourly Trend
CREATE INDEX IF NOT EXISTS idx_shipments_inbound_date 
    ON shipments (inbound_scandate DESC) 
    WHERE is_active = 1 AND inbound_scandate IS NOT NULL;

-- 3. Index tối ưu gom nhóm (GROUP BY) theo bưu cục cho các biểu đồ Pie/Table
CREATE INDEX IF NOT EXISTS idx_shipments_picknetwork 
    ON shipments (picknetworkname) 
    WHERE is_active = 1;

-- 4. Index tối ưu gom nhóm theo trạm Outbound cho Dashboard Outbound
CREATE INDEX IF NOT EXISTS idx_shipments_outbound_date 
    ON shipments (outbound_scandate DESC) 
    WHERE is_active = 1 AND outbound_scandate IS NOT NULL;

-- 5. Index cho bảng Audit để tra cứu nhanh lịch sử ETL theo trạng thái & thời gian
CREATE INDEX IF NOT EXISTS idx_etl_history_status_time 
    ON etl_job_history (status, start_time DESC);

-- 6. Index cho bảng Audit API request log
CREATE INDEX IF NOT EXISTS idx_api_request_timestamp 
    ON api_request_log (request_timestamp DESC);
