# 🔧 Giải pháp sửa luồng Auto Sync 30 phút

> Ngày áp dụng: 2026-07-27
> Trạng thái: ✅ ĐÃ sửa code + test thành công

## 📌 Vấn đề ban đầu

Dashboard báo cáo **thiếu/sai dữ liệu**. Sau khi điều tra, phát hiện **2 vấn đề chồng lên nhau**:

### Vấn đề 1 — Luồng 30 phút gọi sai script
`auto_sync_schedule.py` (line 54 cũ) vẫn gọi `backend_sync/sync_to_sheets.py --sync-only`
(script cũ). Script này fail vì schema SQLite `state.db` đã lệch sau migration Enterprise v2.0:

```
⚠️ Lỗi load đơn từ SQLite: no such column: status_order
❌ Lỗi [InventorySync]: no such column: waybillNo
```

→ Mỗi 30 phút fail → JSON không cập nhật → dashboard hiển thị data cũ.

### Vấn đề 2 — sync_postgre.py chưa đấu nối đầy đủ
Bạn đã chuyển logic sang PostgreSQL (`sync_postgre.py`), nhưng:

- Script cũ `sync_postgre.py` **chỉ xuất 5/9 JSON** (thiếu `linehaul/truck_eta/heatmap`)
- Nó **chỉ đọc CSV** (`full_multi_source_7days_v6.csv`) — không tự refresh
- Nó **không git commit/push** → GitHub không cập nhật → dashboard fetch vẫn data cũ
- `auto_sync_schedule.py` không gọi nó

## ✅ Giải pháp đã áp dụng

### 1. `backend_sync/sync_postgre.py` (sửa lớn)
- **Đổi nguồn dữ liệu**: bỏ đọc CSV, thay bằng `SELECT * FROM enriched.dispatch_enriched`
- **Sửa VALID_FILE**: `Desktop/testing/...` → `backend_sync/config/valid.csv` (file tồn tại)
- **Bỏ** DB_FILE/dwh_v2.db fallback
- **Thêm 3 block xuất JSON mới**: `linehaul.json`, `truck_eta.json`, `heatmap.json`
- **Giữ nguyên** field names mà dashboard đã quen (`Bu cc`, `Trng thi`, `Sc cha`, `Ngy`...)
- Backup tại `sync_postgre.py.bak`

### 2. `auto_sync_schedule.py` (sửa vừa)
- Đổi script gọi: `sync_to_sheets.py` → `sync_postgre.py`
- **XOÁ `git reset --hard HEAD` + `git clean -fd`** (nguy hiểm, xoá file local chưa commit)
- **Thêm xử lý sync.lock stale** (>30 phút hoặc rỗng → tự xoá)
- **Thêm cơ chế lock chính quy**: acquire/release lock an toàn
- **Sửa fake-success**: nếu sync fail → KHÔNG commit/push JSON cũ
- Bỏ `backend_sync/config/valid.csv` khỏi `git add` (không phải output sync)
- Backup tại `auto_sync_schedule.py.bak`

### 3. Dọn dẹp
- Xoá `backend_sync/sync.lock` (file rỗng 0 byte sót lại từ crash cũ)

## 🏗️ Kiến trúc luồng mới

```
[Windows Task Scheduler — 30 phút]
  → auto_sync_schedule.py
    1. cleanup_stale_lock + acquire_lock
    2. git pull --rebase origin main (KHÔNG reset/clean)
    3. python backend_sync/sync_postgre.py
       → SELECT * FROM enriched.dispatch_enriched (PostgreSQL)
       → tổng hợp 85,597 rows → xuất 9 JSON vào data/
    4. NẾU sync OK:
         git add data/*.json src/data/*.json
         git commit -m "chore(data): auto-sync <ts> ICT (from PG)"
         git pull --rebase + git push origin main
       NẾU sync FAIL:
         chỉ log lỗi, KHÔNG push JSON cũ
    5. release_lock

[GitHub Actions deploy.yml — đã có sẵn]
  → nhận push → npm ci + npm run build → deploy GitHub Pages

[Dashboard src/App.tsx]
  → fetch https://raw.githubusercontent.com/.../main/data/*.json
```

## 🧪 Kết quả test (2026-07-27 11:49)

```
python backend_sync/sync_postgre.py
✅ Loaded 85,597 records từ enriched.dispatch_enriched
✅ inventory.json    — 305 dòng
✅ outbound.json     — 61 dòng
✅ backlog.json      — 61 dòng
✅ inbound.json      — 83,083 dòng
✅ arrival.json      — 5,300 dòng
✅ heatmap.json      — 216 dòng
✅ truck_eta.json    — 0 dòng (không có xe đang vận chuyển)
✅ linehaul.json     — giữ nguyên file cũ (cần JFS API)
✅ last_update.json  — rot_hom_nay=0, rot_hom_truoc=85598
```

## ⚠️ Câu hỏi mở / Việc cần làm sau

### 1. 🔴 QUAN TRỌNG — Ai đẩy data mới vào PostgreSQL?
Hiện `rot_hom_nay = 0` tức là **không có đơn tạo hôm nay** trong PG.
→ PostgreSQL `enriched.dispatch_enriched` **không tự refresh**.
→ Cần 1 luồng ingest khác (từ JFS API? từ script khác?) đẩy data mới vào PG mỗi 30p.
Nếu không có luồng này, dashboard vẫn sẽ hiển thị data cũ dù luồng đã sửa.

**Cần bạn xác định**: script nào đang đẩy data vào PG? Nếu chưa có, đây là việc tiếp theo cần làm.

### 2. 🟡 linehaul.json cần JFS API
`linehaul.json` format cũ là `{total_trucks, trucks[]}` từ JFS API.
Script mới **giữ nguyên file cũ** nếu có, không ghi đè.
→ Nếu cần refresh linehaul thực thời, phải tích hợp thêm crawler JFS.

### 3. 🟡 Hardcoded password PG
`sync_postgre.py` line 24: `PGPASSWORD` fallback `"Tien@giang0203"` hardcode.
Nên chuyển sang GitHub Secrets / Windows Credential Manager sau.

### 4. 🟡 inbound.json lớn (49MB)
83,083 dòng có thể khiến dashboard chậm khi load.
→ Có thể tối ưu sau (lọc theo ngày, hoặc gzip).

### 5. 🟡 deploy.yml không có cron 30p
Workflow GitHub chỉ chạy khi có push. KHÔNG nên thêm cron 30p ở GitHub
vì sẽ gây xung đột với luồng local. Hiện trạng là đúng.

## 📁 Files đã thay đổi

| File | Hành động | Backup |
|------|-----------|--------|
| `backend_sync/sync_postgre.py` | Sửa lớn (CSV→PG, +3 JSON) | `sync_postgre.py.bak` |
| `auto_sync_schedule.py` | Sửa vừa (gọi đúng + bỏ git reset + lock) | `auto_sync_schedule.py.bak` |
| `backend_sync/sync.lock` | Xoá (file rỗng) | — |
| `SOLUTION.md` | Tạo mới (file này) | — |

## 🔄 Rollback nếu cần

```bash
# Khôi phục code cũ
cp backend_sync/sync_postgre.py.bak backend_sync/sync_postgre.py
cp auto_sync_schedule.py.bak auto_sync_schedule.py

# Xóa các file mới
rm SOLUTION.md
```
