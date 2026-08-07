# HƯỚNG DẪN VẬN HÀNH & KỊCH BẢN BẢO TRÌ (RUNBOOK)
## HỆ THỐNG DASHBOARD HCM HUB J&T CARGO - RELEASE v2.5 STABLE

---

### 1. QUY TRÌNH CHẠY TỰ ĐỘNG (BACKGROUND SYNC)
- **Tần suất:** Mỗi 30 phút hệ thống Windows Task Scheduler (`Sync_Postgre_30m`) sẽ tự động kích hoạt script `backend_sync/sync_postgre.py`.
- **Tốc độ xử lý:** Luồng kéo 7 ngày JFS API song song với 20 luồng kéo trang (`PAGE_WORKERS = 20`) hoàn tất chỉ trong 1.5 - 3 phút.
- **Log theo dõi:** Mọi nhật ký chạy được ghi lại tại `backend_sync/logs/` hoặc kiểm tra thẻ `Update: HH:MM:SS` ở góc phải Header Dashboard.

---

### 2. KIỂM TRA & XỬ LÝ SỰ CỐ NHANH (TROUBLESHOOTING)

| Sự Cố | Nguyên Nhân | Cách Xử Lý Nhanh |
| :--- | :--- | :--- |
| **Báo cáo trên GitHub Pages chưa đổi** | Trình duyệt lưu Cache HTTP | Bấm `Ctrl + Shift + R` (Hard Refresh) hoặc mở cửa sổ Ẩn danh. |
| **Token JFS API hết hạn** | Tài khoản JFS bị logout | Thao tác đăng nhập lại trên JFS web hoặc xóa cache token trong script. |
| **Vite Dev Server lỗi JS Syntax** | Cache `.vite` bị kẹt | Chạy `npx vite --force --port 5173` để làm sạch cache. |
| **PostgreSQL không kết nối được** | Dịch vụ Postgres 5433 ngắt | Mở Services Windows và Restart `postgresql-x64-16`. |

---

### 3. ĐƯỜNG DẪN TRUY CẬP HỆ THỐNG
- Localhost: `http://localhost:5173/`
- GitHub Pages: `https://lehoangtienpham2395.github.io/sortation-center-layout/`
- Repository GitHub: `https://github.com/lehoangtienpham2395/sortation-center-layout`
