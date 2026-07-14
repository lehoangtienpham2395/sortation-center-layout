-- ==============================================================================
-- MIGRATION 001: INITIAL SCHEMA DEFINITION (TIMESTAMPTZ & NUMERIC(10,2))
-- Compatible with PostgreSQL 16 / Neon Cloud Serverless
-- ==============================================================================

-- 1. Bảng Danh Mục: Khu vực máng trượt và Bưu cục (Master Tables)
CREATE TABLE IF NOT EXISTS chutes_master (
    area_id             VARCHAR(16) PRIMARY KEY,       -- ID máng trượt ('C01', 'A02', 'B05')
    chute_name          VARCHAR(128) NOT NULL,         -- Tên máng trượt ('SG CHỢ LỚN', 'SG HÓC MÔN')
    zone_id             INTEGER NOT NULL,              -- Khu vực (Zone 2, Zone 3)
    chute_type          VARCHAR(32) DEFAULT 'CHUTE',   -- Loại ('CHUTE' hoặc 'TRUCK_SLOT')
    capacity_limit      INTEGER DEFAULT 5000,          -- Ngưỡng cảnh báo tràn máng (đơn)
    is_active           BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS network_master (
    network_name        VARCHAR(128) PRIMARY KEY,      -- Tên bưu cục gốc từ JFS ('BD BÌNH PHƯỚC')
    mapped_area_id      VARCHAR(16) REFERENCES chutes_master(area_id) ON DELETE SET NULL,
    region              VARCHAR(64) DEFAULT 'Miền Nam',
    last_updated        TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Bảng Trung Tâm: Vận Đơn (Shipments - Vòng đời từng kiện hàng)
CREATE TABLE IF NOT EXISTS shipments (
    waybillno           VARCHAR(32) PRIMARY KEY,       -- Mã vận đơn (Primary Key tuyệt đối)
    data_source         VARCHAR(32) NOT NULL,          -- Nguồn dữ liệu ('JFS_INBOUND', 'JFS_DISPATCH'...)
    weight              NUMERIC(10,2) DEFAULT 0.00,    -- Cân nặng thực tế (kg) - Chuẩn xác từng 0.01 kg
    picknetworkname     VARCHAR(128),                  -- Bưu cục nhận / gửi
    dispatch_plan       VARCHAR(64),                   -- Kế hoạch điều phối
    pickup_time         TIMESTAMPTZ,                   -- Thời gian lấy hàng (TIMESTAMPTZ)
    pickup_label        VARCHAR(32),                   -- Nhãn nhận hàng ('Đã lấy hàng'...)
    pickup_ontime       VARCHAR(32),                   -- Trạng thái đúng giờ lấy hàng
    dispatchnetworktime TIMESTAMPTZ,                   -- Thời gian điều phối bưu cục (TIMESTAMPTZ)
    next_station        VARCHAR(128),                  -- Trạm kế tiếp
    tuyen               VARCHAR(64),                   -- Tuyến vận chuyển ('Tuyến 1', 'Tuyến 2'...)
    rank                VARCHAR(16),                   -- Xếp hạng ưu tiên / kích thước
    inbound_network     VARCHAR(128),                  -- Bưu cục/trạm quét Inbound
    inbound_scandate    TIMESTAMPTZ,                   -- Thời gian quét Inbound (TIMESTAMPTZ)
    outbound_scandate   TIMESTAMPTZ,                   -- Thời gian quét Outbound (TIMESTAMPTZ)
    arrival_time        TIMESTAMPTZ,                   -- Thời gian quét Arrival tại trung tâm (TIMESTAMPTZ)
    dispatch_actual     VARCHAR(64),                   -- Điều phối thực tế
    status_order        VARCHAR(64) NOT NULL,          -- Trạng thái ('Đang trong HUB', 'Đã rời HUB'...)
    time_ref            TIMESTAMPTZ,                   -- Mốc thời gian tham chiếu tính tuổi đơn (TIMESTAMPTZ)
    is_backlog          SMALLINT DEFAULT 0,            -- Cờ tồn đọng (1 = Tồn đọng > 24h, 0 = Bình thường)
    is_active           SMALLINT DEFAULT 1 NOT NULL,   -- Cờ hoạt động (1 = Đang xử lý, 0 = Đã xong/Rời HUB)
    created_at          TIMESTAMPTZ DEFAULT NOW(),     -- Thời điểm tạo record lần đầu
    last_updated        TIMESTAMPTZ DEFAULT NOW()      -- Thời điểm cập nhật cuối cùng
);

-- 2.1. Sanitize any existing TEXT/VARCHAR timestamp columns (if migrated from SQLite/legacy scheme)
DO $$
BEGIN
    UPDATE shipments SET inbound_scandate = NULL WHERE inbound_scandate::text = 'Backlog' OR inbound_scandate::text = '' OR NOT (inbound_scandate::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}');
    UPDATE shipments SET outbound_scandate = NULL WHERE outbound_scandate::text = 'Backlog' OR outbound_scandate::text = '' OR NOT (outbound_scandate::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}');
    UPDATE shipments SET pickup_time = NULL WHERE pickup_time::text = 'Backlog' OR pickup_time::text = '' OR NOT (pickup_time::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}');
    UPDATE shipments SET dispatchnetworktime = NULL WHERE dispatchnetworktime::text = 'Backlog' OR dispatchnetworktime::text = '' OR NOT (dispatchnetworktime::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}');
    UPDATE shipments SET arrival_time = NULL WHERE arrival_time::text = 'Backlog' OR arrival_time::text = '' OR NOT (arrival_time::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}');
    UPDATE shipments SET time_ref = NULL WHERE time_ref::text = 'Backlog' OR time_ref::text = '' OR NOT (time_ref::text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}');
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- 2.2. Ensure columns are native TIMESTAMPTZ
DO $$
BEGIN
    ALTER TABLE shipments ALTER COLUMN inbound_scandate TYPE TIMESTAMPTZ USING NULLIF(TRIM(inbound_scandate::text), '')::timestamptz;
    ALTER TABLE shipments ALTER COLUMN outbound_scandate TYPE TIMESTAMPTZ USING NULLIF(TRIM(outbound_scandate::text), '')::timestamptz;
    ALTER TABLE shipments ALTER COLUMN pickup_time TYPE TIMESTAMPTZ USING NULLIF(TRIM(pickup_time::text), '')::timestamptz;
    ALTER TABLE shipments ALTER COLUMN dispatchnetworktime TYPE TIMESTAMPTZ USING NULLIF(TRIM(dispatchnetworktime::text), '')::timestamptz;
    ALTER TABLE shipments ALTER COLUMN arrival_time TYPE TIMESTAMPTZ USING NULLIF(TRIM(arrival_time::text), '')::timestamptz;
    ALTER TABLE shipments ALTER COLUMN time_ref TYPE TIMESTAMPTZ USING NULLIF(TRIM(time_ref::text), '')::timestamptz;
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- 3. Bảng Vận Hành & Audit: Lịch sử ETL Job & Cấu hình Hệ thống
CREATE TABLE IF NOT EXISTS etl_job_history (
    job_id              VARCHAR(64) PRIMARY KEY,       -- UUID hoặc Job ID ('sync-20260714-170000')
    start_time          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_time            TIMESTAMPTZ,
    duration_sec        REAL,
    status              VARCHAR(32) NOT NULL,          -- ('SUCCESS', 'FAILED', 'RUNNING')
    records_processed   INTEGER DEFAULT 0,
    error_message       TEXT,
    triggered_by        VARCHAR(64) DEFAULT 'CRON',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS system_config (
    config_key          VARCHAR(64) PRIMARY KEY,       -- Khóa ('ETL_PAGE_WORKERS', 'AUTO_BACKFILL_WEIGHT')
    config_value        TEXT NOT NULL,
    description         VARCHAR(256),
    last_updated_by     VARCHAR(64) DEFAULT 'SYSTEM',
    last_updated        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_request_log (
    log_id              BIGSERIAL PRIMARY KEY,
    trace_id            VARCHAR(64) NOT NULL,          -- Trace ID định danh request
    endpoint            VARCHAR(128) NOT NULL,
    client_ip           VARCHAR(64),
    status_code         INTEGER NOT NULL,
    execution_ms        REAL NOT NULL,
    request_timestamp   TIMESTAMPTZ DEFAULT NOW()
);
