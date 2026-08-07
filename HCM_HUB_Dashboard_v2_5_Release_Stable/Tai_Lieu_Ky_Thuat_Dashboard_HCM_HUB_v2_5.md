# TÀI LIỆU KỸ THUẬT VẬN HÀNH & KIẾN TRÚC HỆ THỐNG
## DASHBOARD BÁO CÁO KHO HCM HUB (J&T CARGO) - VERSION 2.5 STABLE
**Quy trình End-to-End: JFS API → PostgreSQL (28 Cột) → JSON Realtime → React UI**

---

### 1. TỔNG QUAN KIẾN TRÚC & NGUYÊN TẮC VẬN HÀNH
Hệ thống Dashboard HCM HUB hoạt động theo kiến trúc ETL phân tán kết hợp CSDL PostgreSQL Local và hosting tĩnh GitHub Pages:
- **Phase 1 (Data Ingestion):** `pipeline_unified_v6.py` thực hiện kéo dữ liệu song song 7 ngày từ 8 nguồn JFS API. Mức độ song song được tối ưu với `PAGE_WORKERS = 20` (kéo 20 trang API đồng thời) và `POOL_SIZE = 40`.
- **Phase 2 (PostgreSQL Data Processing & Micro-JSON Exporter):** `sync_postgre.py` lưu trữ 28 cột chuẩn hóa vào `enriched.dispatch_enriched` trong PostgreSQL (cổng 5433). Đồng thời thực hiện xuất đồng bộ các gói dữ liệu Micro-JSON (`inbound_kpi_summary.json`, `inbound_truck_eta.json`, `inventory.json`, `last_update.json`...) vào **4 vị trí đồng thời** (`data/`, `data/live/`, `public/data/`, `public/data/live/`) để phục vụ cả Localhost lẫn GitHub Pages Build.
- **Phase 3 (Git Synchronization & Retention):** Tự động đẩy Git commit với danh sách `ROLLING_FILES` chứa 35+ file dữ liệu rolling và thực hiện dọn dẹp dữ liệu PostgreSQL retention 90 ngày (`DELETE FROM raw.scan_logs WHERE scan_time < CURRENT_DATE - 90`).

---

### 2. QUY TẮC NGHIỆP VỤ ĐÃ CHỐT VÀ NÂNG CẤP TRONG VERSION 2.5

#### 2.1 Màn Hình Operational Monitor (Master Layout)
- **Top Card Title & Tỉ Lệ Lấp Đầy (Capacity Fill Rate %):**
  - Tiêu đề thẻ trên cùng được chốt chuẩn là **"TỈ LỆ LẤP ĐẦY"**.
  - Công thức tính:
    $$	ext{Tỉ Lệ Lấp Đầy} = \left(rac{\sum 	ext{tCur}}{\sum 	ext{tCap}}ight) 	imes 100$$
    Trong đó $\sum 	ext{tCur}$ là tổng số đơn hiện có trên các kệ và $\sum 	ext{tCap}$ là tổng sức chứa của toàn bộ các kệ bãi.
- **Thẻ Tỉ Lệ Outbound:**
  - Tiêu đề thẻ phía dưới là **"Tỉ lệ Outbound"**.
  - Công thức tính:
    $$	ext{outboundRate} = rac{	ext{tCur}}{	ext{tCur} + 	ext{tBacklog}}$$
- **Thanh Chữ Chạy Realtime (Ticker Bar):**
  - Tích hợp hiệu ứng cuộn mượt mà `@keyframes inlineMarquee` trực tiếp trong CSS.
  - Tự động dịch chuyển `left` offset theo trạng thái Sidebar (`left-12` khi thu gọn 48px, `left-40` khi mở rộng 160px) để không bao giờ bị đè hoặc khuất chữ.

#### 2.2 Màn Hình Inbound Dashboard
- **Truck Forecast ETA +36h Transport Rule:**
  - Tất cả các xe Linehaul xuất phát từ **BN HUB** đều được áp dụng quy tắc cộng **+36 tiếng** vào mốc giờ xuất bãi (`ETA = actualDeparture + 36h`).
  - Giữ lại danh sách các xe đã quét cổng HUB (`actualArrival` / `shipmentState = 4`) nhưng chưa quét inbound hàng hóa (`flag_inbound = 0`) trong danh sách xe chờ nhập kho ngày Hôm nay (05/08) và Ngày mai (06/08).
- **KPI Volume Card Filter:**
  - Trạng thái hợp lệ cho thẻ Volume đạt chuẩn exact ~13.1k đơn bằng cách bao gồm đủ 4 trạng thái: `'Inbound'`, `'Transporting'`, `'Pickup Done'`, `'Created'`.

---

### 3. HƯỚNG DẪN KÍCH HOẠT & THEO DÕI

1. **Khởi chạy Luồng Đồng Bộ Tự Động (Kích hoạt Task Scheduler 30 phút/lần):**
   ```powershell
   powershell -ExecutionPolicy Bypass -File ./backend_sync/setup_sync_postgre_task.ps1
   ```
2. **Khởi chạy Localhost Dev Server:**
   ```bash
   npx vite --host 0.0.0.0 --port 5173
   ```
3. **Chạy Luồng Đồng Bộ Bằng Tay Ngay Lập Tức:**
   ```bash
   python backend_sync/sync_postgre.py
   ```
