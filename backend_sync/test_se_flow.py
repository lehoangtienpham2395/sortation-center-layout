import sys
import os
import json
import gzip
import math
import time
import sqlite3
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add current folder to sys.path to import from sync_to_sheets
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sync_to_sheets import (
    TokenManager, auth_post, pull_forecast, pull_dispatch,
    get_operating_date, load_json,
    URL_FORECAST, URL_DISPATCH, COUNTRY_ID, VALID_FILE, DB_FILE
)

def main():
    print("🚀 BẮT ĐẦU CHẠY TEST LUỒNG DỮ LIỆU CỤM SE BẰNG BỘ LỌC SORTCODE...")
    
    # 1. Đọc danh sách bưu cục thuộc cụm SE từ valid.csv
    se_buucucs = set()
    se_sortcodes = []
    d_buucuc = {}
    d_tuyen = {}
    d_rank = {}
    try:
        if os.path.exists(VALID_FILE):
            df_v = pd.read_csv(VALID_FILE, encoding='utf-8-sig', dtype=str)
            df_v.columns = df_v.columns.str.strip()
            
            # Khởi tạo các từ điển mapping
            d_buucuc = {str(k).strip(): str(v).strip() for k, v in df_v.set_index('Bưu cục')['Bưu cục final'].dropna().to_dict().items()}
            d_tuyen = {str(k).strip(): str(v).strip() for k, v in df_v.set_index('Bưu cục final')['Tuyến'].dropna().to_dict().items()}
            d_rank = {str(k).strip(): str(v).strip() for k, v in df_v.set_index('Bưu cục final')['Rank'].dropna().to_dict().items()}
            
            df_se = df_v[df_v['Vùng lớn'].str.startswith('SE', na=False)]
            for _, r in df_se.iterrows():
                name = str(r.get('Bưu cục') or r.get('Bưu cục final') or '').strip().upper()
                code = str(r.get('sortcode') or '').strip().upper()
                if name:
                    se_buucucs.add(name)
                if code and code != 'NAN' and code not in se_sortcodes:
                    se_sortcodes.append(code)
            print(f"   👉 Đã nạp danh sách cụm SE: {len(se_buucucs)} bưu cục, {len(se_sortcodes)} sortcode: {se_sortcodes}")
        else:
            print("   ❌ Không tìm thấy file valid.csv!")
            return
    except Exception as e:
        print(f"   ❌ Lỗi đọc và phân tích valid.csv: {e}")
        return

    # 2. Khởi tạo TokenManager cho user 660085
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    
    print("🔐 Đang đăng nhập tài khoản 660085...")
    token_mgr = TokenManager(session, "660085", "246@Hoang", COUNTRY_ID)
    try:
        token = token_mgr.get_token()
        print("   ✅ Đăng nhập thành công! Token:", token[:15] + "...")
    except Exception as e:
        print(f"   ❌ Đăng nhập thất bại: {e}")
        return

    # 3. Thiết lập khoảng thời gian: Từ 01/07 đến nay
    DATE_START = "2026-07-01 00:00:00"
    now_vn = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    DATE_END = now_vn.strftime('%Y-%m-%d %H:%M:%S')
    print(f"📅 Khoảng thời gian test: {DATE_START} → {DATE_END}")

    # 4. Load headers và payloads
    fh = load_json(os.path.join(os.path.dirname(__file__), "config", "forecastheaders.json"))
    fp = load_json(os.path.join(os.path.dirname(__file__), "config", "forecastpayload.json"))
    for k in ['timeStart', 'inputTimeStart']: fp[k] = DATE_START
    for k in ['timeEnd', 'inputTimeEnd']:     fp[k] = DATE_END

    dh = load_json(os.path.join(os.path.dirname(__file__), "config", "dispatchheaders.json"))
    dp_cfg = load_json(os.path.join(os.path.dirname(__file__), "config", "dispatchpayload.json"))
    dp_cfg['startInputTime'] = DATE_START
    dp_cfg['endInputTime'] = DATE_END

    # 5. Đọc thông tin lịch sử từ SQLite để lấy mốc Inbound/Pickup/Forecast cũ nếu có
    db_waybill_times = {}
    if os.path.exists(DB_FILE):
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT waybillNo, Pickup_time, dispatchNetworkTime, inbound_scanDate, status_order FROM inventory")
            rows = c.fetchall()
            for r in rows:
                wb = r[0]
                db_waybill_times[wb] = {
                    'pickup_time': r[1] if r[1] else '',
                    'forecast_time': r[2] if r[2] else '',
                    'inbound_time': r[3] if r[3] else '',
                    'status_order': r[4] if r[4] else ''
                }
            conn.close()
            print(f"ℹ️ Loaded {len(db_waybill_times):,} mốc thời gian lịch sử từ SQLite.")
        except Exception as e_db:
            print(f"⚠️ Lỗi đọc SQLite: {e_db}")

    # 6. Kéo dữ liệu cho từng bưu cục của cụm SE
    awb_records = {}

    for sc in se_sortcodes:
        print(f"\n⚡ Truy vấn cho bưu cục sortcode: {sc}...")
        
        fp_sc = {**fp, 'pickFinanceCode': '', 'pickNetworkCode': sc}
        dp_sc = {**dp_cfg, 'pickNetworkCode': sc}
        forecast_raw = pull_forecast(session, token_mgr, fh, fp_sc, label=f'Forecast_{sc}')
        dispatch_raw = pull_dispatch(session, token_mgr, dh, dp_sc, label=f'Dispatch_{sc}')
        
        # A. Xử lý Dispatch
        dispatch_count = 0
        for r in dispatch_raw:
            wb = str(r.get('waybillNo') or r.get('waybillId', '')).strip()
            if not wb or wb.lower() in ('nan', 'none', ''):
                continue
                
            fc = str(r.get('pickNetworkName', '')).strip()
            fc_mapped = d_buucuc.get(fc, fc)
            
            weight = float(r.get('packageChargeWeight') or r.get('weight') or 0.0)
            dispatch_time = str(r.get('dispatchNetworkTime') or '').strip()
            status_dp = str(r.get('orderStatusName') or '').strip()
            update_time = str(r.get('updateTime') or '').strip()
            pickup_time = update_time if (status_dp == 'Đã lấy hàng' and update_time) else ''
            
            dispatch_count += 1
            awb_records[wb] = {
                'waybill': wb,
                'fc': fc_mapped,
                'weight': weight,
                'forecast_time': dispatch_time if (dispatch_time and dispatch_time.lower() not in ('nan', 'none')) else '',
                'pickup_time': pickup_time,
                'inbound_time': '',
                'source': 'Dispatch'
            }

        # B. Xử lý Forecast (merge vào Dispatch hoặc tạo mới)
        forecast_count = 0
        for r in forecast_raw:
            wb = str(r.get('waybillNo', '')).strip()
            if not wb or wb.lower() in ('nan', 'none', ''):
                continue
                
            fc = str(r.get('pickNetworkName', '')).strip()
            fc_mapped = d_buucuc.get(fc, fc)
            
            forecast_count += 1
            delivery_time = str(r.get('deliveryTime') or '').strip()
            if delivery_time.lower() in ('nan', 'none'):
                delivery_time = ''
            weight = float(r.get('loadWeight') or 0.0)
            
            if wb in awb_records:
                if not awb_records[wb]['pickup_time'] and delivery_time:
                    awb_records[wb]['pickup_time'] = delivery_time
            else:
                awb_records[wb] = {
                    'waybill': wb,
                    'fc': fc_mapped,
                    'weight': weight,
                    'forecast_time': '',
                    'pickup_time': delivery_time,
                    'inbound_time': '',
                    'source': 'Forecast'
                }
        print(f"   👉 Tải xong: Lọc được {forecast_count} Forecast, {dispatch_count} Dispatch.")

    print(f"\n🔍 Tổng kết: Tìm thấy {len(awb_records):,} đơn thuộc cụm SE sau khi gộp Forecast/Dispatch.")

    # C. Ánh xạ các mốc thời gian lịch sử từ SQLite (nhất là Inbound)
    for wb, rec in awb_records.items():
        hist = db_waybill_times.get(wb)
        if hist:
            if hist['inbound_time'] and not rec['inbound_time']:
                rec['inbound_time'] = hist['inbound_time']
            if hist['pickup_time'] and not rec['pickup_time']:
                rec['pickup_time'] = hist['pickup_time']
            if hist['forecast_time'] and not rec['forecast_time']:
                rec['forecast_time'] = hist['forecast_time']

    # D. Chuẩn hóa ngày vận hành & Trạng thái đơn hàng
    unique_rows = []
    for wb, rec in awb_records.items():
        ib_time = rec['inbound_time']
        pk_time = rec['pickup_time']
        fc_time = rec['forecast_time']
        
        # Xử lý chuỗi NaT/nan rác
        for k in ['inbound_time', 'pickup_time', 'forecast_time']:
            val = rec[k]
            if val and str(val).lower() in ('nan', 'none', 'nat'):
                rec[k] = ''
        
        ib_time = rec['inbound_time']
        pk_time = rec['pickup_time']
        fc_time = rec['forecast_time']
        
        # Priority engine
        if ib_time:
            status = "Đã về Hub"
        elif pk_time:
            status = "Lấy hàng thành công"
        elif fc_time:
            status = "Điều phối bưu cục"
        else:
            status = "Forecast"
            
        op_date_ib = get_operating_date(ib_time) if ib_time else ""
        
        fc_time_temp = fc_time if fc_time else (pk_time if status == 'Forecast' else '')
        op_date_fc = get_operating_date(fc_time_temp) if fc_time_temp else ""
        
        op_date_pk = ""
        if status not in ('Forecast', 'Đã điều phối bưu cục') and pk_time:
            op_date_pk = get_operating_date(pk_time)
            
        loai_rot = "Rớt hôm nay"
        if op_date_fc:
            if op_date_pk:
                if op_date_fc != op_date_pk:
                    loai_rot = "Rớt hôm trước"
            elif op_date_fc < get_operating_date(now_vn.strftime('%Y-%m-%d %H:%M:%S')):
                loai_rot = "Rớt hôm trước"
                
        # Định dạng Hour
        ib_hour = pd.to_datetime(ib_time).strftime('%Y-%m-%d %H:00') if ib_time else ""
        fc_hour = pd.to_datetime(fc_time_temp).strftime('%Y-%m-%d %H:00') if fc_time_temp else ""
        pk_hour = pd.to_datetime(pk_time).strftime('%Y-%m-%d %H:00') if pk_time else ""
        
        unique_rows.append({
            'Bưu cục': rec['fc'],
            'Trạng thái': status,
            'weight': rec['weight'],
            'Ngày vận hành_Inbound': op_date_ib,
            'Ngày vận hành_Forecast': op_date_fc,
            'Ngày vận hành_Pickup': op_date_pk,
            'Inbound Hour': ib_hour,
            'Forecast Time': fc_hour,
            'Pickup Time': pk_hour,
            'Loại rớt': loai_rot,
            'waybill': wb
        })

    # E. Áp dụng Carryover logic cho các đơn quá khứ chưa về Hub
    current_op_date = get_operating_date(now_vn.strftime('%Y-%m-%d %H:%M:%S'))
    projected_rows = []
    for r in unique_rows:
        projected_rows.append(r)
        if r['Trạng thái'] != 'Đã về Hub' and r['Trạng thái'] != 'Đã nhập hàng':
            was_picked_before_today = r['Ngày vận hành_Pickup'] and r['Ngày vận hành_Pickup'] < current_op_date
            if not was_picked_before_today:
                if r['Ngày vận hành_Forecast'] and r['Ngày vận hành_Forecast'] < current_op_date:
                    dup = r.copy()
                    dup['Ngày vận hành_Forecast'] = current_op_date
                    dup['Loại rớt'] = 'Rớt hôm trước'
                    projected_rows.append(dup)

    # 8. Gom nhóm tạo định dạng dữ liệu Inbound
    grouped_ib = {}
    for r in projected_rows:
        key = (
            r['Bưu cục'], r['Trạng thái'],
            r['Ngày vận hành_Inbound'], r['Ngày vận hành_Forecast'], r['Ngày vận hành_Pickup'],
            r['Inbound Hour'], r['Forecast Time'], r['Pickup Time'], r['Loại rớt']
        )
        if key not in grouped_ib:
            grouped_ib[key] = {'volume': 0, 'weight': 0.0}
        grouped_ib[key]['volume'] += 1
        grouped_ib[key]['weight'] += r['weight']
        
    final_ib_rows = []
    for (fc_name, status, op_ib, op_fc, op_pk, ib_hour, fc_hour, pk_hour, loai_rot), stats in grouped_ib.items():
        final_ib_rows.append({
            'Bu cc': fc_name,
            'Trng thi': status,
            'Volume': stats['volume'],
            'Weight': int(stats['weight']),
            'Ngy vn hnh_Inbound': op_ib,
            'Ngy vn hnh_Forecast': op_fc,
            'Ngy vn hnh_Pickup': op_pk,
            'Inbound Hour': ib_hour,
            'Forecast Time': fc_hour,
            'Pickup Time': pk_hour,
            'Loi rt': loai_rot
        })
    df_ib_aggregated = pd.DataFrame(final_ib_rows)

    # 9. Gom nhóm tạo định dạng dữ liệu Inventory
    # Mô phỏng master_chutes cho cụm SE dựa trên tên bưu cục
    se_chutes = {}
    zone = 3  # Giả lập Zone 3 cho cụm SE
    area_idx = 1
    for name in sorted(se_buucucs):
        area_id = f"SE{area_idx:03d}"
        se_chutes[(zone, area_id)] = {
            "zone": zone,
            "area_id": area_id,
            "name": name,
            "capacity": "780"
        }
        area_idx += 1

    inventory_volumes = {}
    for r in unique_rows:
        name_upper = r['Bưu cục'].strip().upper()
        status = r['Trạng thái']
        if status == 'Đã về Hub':
            status = 'Đang trên bãi'  # Map sang trạng thái Inventory
        
        # Chỉ tính các trạng thái thuộc Inventory
        if status in ('Đang trên bãi', 'Đã lấy hàng', 'Đã điều phối bưu cục', 'Đã rời HUB'):
            key = (name_upper, status)
            if key not in inventory_volumes:
                inventory_volumes[key] = {'volume': 0, 'weight': 0.0}
            inventory_volumes[key]['volume'] += 1
            inventory_volumes[key]['weight'] += r['weight']

    final_inv_rows = []
    for (z, area_id), info in se_chutes.items():
        name_upper = info["name"].strip().upper()
        for status in ['Đang trên bãi', 'Đã lấy hàng', 'Đã điều phối bưu cục', 'Đã rời HUB']:
            vol_wt = inventory_volumes.get((name_upper, status), {'volume': 0, 'weight': 0})
            final_inv_rows.append({
                'Zone': info['zone'],
                'AreaID': info['area_id'],
                'Bu cc': info['name'],
                'Trng thi': status,
                'Volume': vol_wt['volume'],
                'Weight': int(vol_wt['weight']),
                'Sc cha': info['capacity'],
                'Ngy': current_op_date
            })
    df_inv_aggregated = pd.DataFrame(final_inv_rows)

    # 9.5. Nhập dữ liệu cụm SE vào SQLite (state.db)
    print("\n💾 Đang ghi dữ liệu cụm SE vào SQLite (state.db)...")
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode = WAL")
        c.execute("PRAGMA synchronous = OFF")
        
        upsert_query = """
            INSERT INTO inventory (
                waybillNo, data_source, weight, pickNetworkName, dispatch_plan,
                Pickup_time, pickup_label, Pickup_ontime, dispatchNetworkTime,
                next_station, Tuyến, Rank, inbound_network, inbound_scanDate,
                outbound_scanDate, dispatch_actual, status_order, time_ref, last_updated
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, CURRENT_TIMESTAMP
            )
            ON CONFLICT(waybillNo) DO UPDATE SET
                data_source = CASE WHEN excluded.data_source != 'Forecast' THEN excluded.data_source ELSE inventory.data_source END,
                weight = CASE WHEN excluded.weight > 0 THEN excluded.weight ELSE inventory.weight END,
                pickNetworkName = CASE WHEN excluded.pickNetworkName != '' THEN excluded.pickNetworkName ELSE inventory.pickNetworkName END,
                Pickup_time = CASE WHEN (inventory.Pickup_time = '' OR inventory.Pickup_time IS NULL OR inventory.Pickup_time = 'NaT') AND excluded.Pickup_time != '' THEN excluded.Pickup_time ELSE inventory.Pickup_time END,
                dispatchNetworkTime = CASE WHEN (inventory.dispatchNetworkTime = '' OR inventory.dispatchNetworkTime IS NULL OR inventory.dispatchNetworkTime = 'NaT') AND excluded.dispatchNetworkTime != '' THEN excluded.dispatchNetworkTime ELSE inventory.dispatchNetworkTime END,
                inbound_scanDate = CASE WHEN (inventory.inbound_scanDate = '' OR inventory.inbound_scanDate IS NULL OR inventory.inbound_scanDate = 'NaT') AND excluded.inbound_scanDate != '' THEN excluded.inbound_scanDate ELSE inventory.inbound_scanDate END,
                status_order = excluded.status_order,
                time_ref = excluded.time_ref,
                last_updated = CURRENT_TIMESTAMP
        """
        
        records_to_upsert = []
        for r in unique_rows:
            wb = r['waybill']
            status = r['Trạng thái']
            rec = awb_records[wb]
            ib_time = rec['inbound_time']
            pk_time = rec['pickup_time']
            fc_time = rec['forecast_time']
            
            t_ref = ib_time if ib_time else (pk_time if pk_time else fc_time)
            tuyen = d_tuyen.get(rec['fc'], '')
            rank = d_rank.get(rec['fc'], '')
            
            records_to_upsert.append((
                wb, rec['source'], rec['weight'], rec['fc'], tuyen,
                pk_time, '', '', fc_time,
                '', tuyen, rank, rec['fc'], ib_time,
                '', '', status, t_ref
            ))
            
        c.executemany(upsert_query, records_to_upsert)
        conn.commit()
        conn.close()
        print(f"   ✅ Đã import {len(records_to_upsert)} vận đơn SE vào SQLite thành công.")
    except Exception as e_db_import:
        print(f"   ❌ Lỗi import dữ liệu SE vào SQLite: {e_db_import}")

    # 10. Ghi dữ liệu ra file output test
    out_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(out_dir, exist_ok=True)
    
    ib_out_path = os.path.join(out_dir, "test_se_inbound.json")
    inv_out_path = os.path.join(out_dir, "test_se_inventory.json")
    
    df_ib_aggregated.to_json(ib_out_path, orient="records", force_ascii=False)
    df_inv_aggregated.to_json(inv_out_path, orient="records", force_ascii=False)
    
    print("\n==================================================")
    print("🎉 HOÀN TẤT CHẠY TEST LUỒNG DỮ LIỆU CỤM SE BẰNG FILTER SORTCODE!")
    print(f"📂 File Inbound test: {ib_out_path} ({len(df_ib_aggregated)} dòng)")
    print(f"📂 File Inventory test: {inv_out_path} ({len(df_inv_aggregated)} dòng)")
    print(f"📊 Tổng số vận đơn SE thu thập được: {len(awb_records)} đơn.")
    print("==================================================")

if __name__ == "__main__":
    main()
