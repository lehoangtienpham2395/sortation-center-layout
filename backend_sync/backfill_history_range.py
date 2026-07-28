"""
backfill_history_range.py — Kéo dữ liệu theo từng ngày từ 2026-06-30 đến nay
=============================================================================
1. Kéo JFS API cho từng ngày (00:00:00 -> 23:59:59)
2. Upsert vào PostgreSQL enriched.dispatch_enriched
3. Atomic refresh cờ vận hành (flag_created, flag_pickup, flag_arrival, flag_inbound, flag_outbound...)
4. Đóng gói snapshot data/history/YYYY-MM-DD.json & cập nhật data/history_index.json
5. Cập nhật các bảng phụ schema reporting (inbound_daily, outbound_daily, kpi_daily...)
6. Git push từng ngày lên GitHub
"""
import sys, os, time, datetime, json, subprocess
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
from psycopg2.extras import execute_values
import pipeline_unified_v6 as pipe
from sync_postgre import get_pg_conn, refresh_operational_flags, BASE_DIR, DATA_DIR, VALID_FILE
from snapshot_daily import load_valid_csv, get_op_date, clean_ts_str

ZONE_MAP = {'SR0001': '1', 'BNI001': '1', '1': '1', '2': '2', '3': '3'}

tz_vn = ZoneInfo('Asia/Ho_Chi_Minh')
now_vn = datetime.datetime.now(tz_vn)

# 1. Danh sách ngày từ 2026-06-30 đến hôm nay (2026-07-28)
START_DATE = datetime.date(2026, 6, 30)
END_DATE   = now_vn.date()

dates = []
curr = START_DATE
while curr <= END_DATE:
    dates.append(curr.strftime('%Y-%m-%d'))
    curr += datetime.timedelta(days=1)

print(f"📋 Bắt đầu luồng kéo dữ liệu theo từng ngày ({len(dates)} ngày: {dates[0]} → {dates[-1]})\n")

session_main = pipe.build_session()
tkn_main = pipe.TokenManager(session_main, pipe.ACCOUNT, pipe.PASSWORD, label='660021')
tkn_main.get_token()

dh_headers = pipe.load_json(pipe.cfg('dispatchheaders.json'))

HIST_DIR = os.path.join(DATA_DIR, "history")
IDX_FILE = os.path.join(DATA_DIR, "history_index.json")
os.makedirs(HIST_DIR, exist_ok=True)

dict_zone, dict_area, dict_station = load_valid_csv()


import re

def extract_ma10(val):
    if not val or str(val).strip() == '': return ''
    ms = re.findall(r'[A-Z]{2,3}\d{3}[A-Z0-9]', str(val))
    return ms[0] if ms else ''


def process_single_date(d_str: str):
    print(f"\n============================================================")
    print(f"📅 [GIAI ĐOẠN {d_str}] Bắt đầu xử lý ngày vận hành {d_str}")
    print(f"============================================================")

    # 1. Kéo JFS API cho ngày d_str
    dp_payload = pipe.load_json(pipe.cfg('dispatchpayload.json'))
    dp_payload['startInputTime'] = f"{d_str} 00:00:00"
    dp_payload['endInputTime']   = f"{d_str} 23:59:59"

    print(f"1. Kéo Dispatch JFS API ({d_str} 00:00:00 -> 23:59:59)...")
    recs = pipe.pull_dispatch(session_main, tkn_main, dh_headers, dp_payload, label=f"Dispatch_{d_str}")
    print(f"   🟢 Lấy thành công {len(recs):,} vận đơn dispatch")

    # 2. Upsert vào PostgreSQL
    conn = get_pg_conn()
    cur = conn.cursor()

    if recs:
        batch = []
        for r in recs:
            wb  = pipe.clean_wb(r.get('waybillId') or r.get('waybillNo'))
            ct  = str(r.get('inputTime') or r.get('dispatchNetworkTime') or '').strip()
            pt  = str(r.get('pickTime') or '').strip()
            pkn = str(r.get('pickNetworkName') or '').strip()
            pk2 = str(r.get('realPickNetworkName') or '').strip()
            stn = pipe.clean_status_sys(str(r.get('orderStatusName') or '').strip())
            dr  = str(r.get('terminalDispatchCode') or '').strip().upper()
            dc  = extract_ma10(dr) or dr
            num = int(r.get('packageNumber') or 1)
            wt  = float(r.get('packageChargeWeight') or 0.0)
            ac  = str(r.get('proxyAreaCode') or '').strip()
            ft  = str(r.get('flowTypeDesc') or '').strip()

            if wb and ct:
                batch.append((
                    wb, 'pipeline_v6', stn or 'Created', ct or None,
                    pkn or None, dc or None, num, wt,
                    pk2 or None, pt or None, None, ac or None, ft or None,
                    d_str
                ))

        upsert_sql = """
            INSERT INTO enriched.dispatch_enriched (
                tracking, data_source, status_sys, created_time,
                pickup_station, dispatch_code, orders_num, orders_weight,
                pickup_station2, pickup_time, pickup_ontime, areacode, flowtypedesc,
                operation_date_created
            ) VALUES %s
            ON CONFLICT (tracking) DO UPDATE SET
                status_sys               = COALESCE(NULLIF(EXCLUDED.status_sys, ''), enriched.dispatch_enriched.status_sys),
                pickup_time              = COALESCE(EXCLUDED.pickup_time, enriched.dispatch_enriched.pickup_time),
                pickup_station           = COALESCE(NULLIF(EXCLUDED.pickup_station, ''), enriched.dispatch_enriched.pickup_station),
                pickup_station2          = COALESCE(NULLIF(EXCLUDED.pickup_station2, ''), enriched.dispatch_enriched.pickup_station2),
                areacode                 = COALESCE(NULLIF(EXCLUDED.areacode, ''), enriched.dispatch_enriched.areacode),
                flowtypedesc             = COALESCE(NULLIF(EXCLUDED.flowtypedesc, ''), enriched.dispatch_enriched.flowtypedesc),
                operation_date_created   = COALESCE(EXCLUDED.operation_date_created, enriched.dispatch_enriched.operation_date_created),
                last_updated             = CURRENT_TIMESTAMP;
        """
        execute_values(cur, upsert_sql, batch, page_size=2000)
        conn.commit()
        print(f"   🟢 Upsert PostgreSQL xong: {len(batch):,} dòng")

    # 3. Refresh operational flags
    refresh_operational_flags()

    # 4. Query PostgreSQL cho ngày d_str để đóng gói History Snapshot
    cur.execute("""
        SELECT tracking, status_sys, created_time, pickup_station, dispatch_code,
               orders_num, orders_weight, pickup_time, areacode, flowtypedesc,
               next_station, round, rank, inbound_scandate, outbound_scandate, arrival_scandate,
               trip_code, transporing_time, transported_time, operation_date_created,
               operation_date_inbound, is_backlog, is_active, is_completed, is_rebound, return_count,
               inbound_scandate_2, operation_date_inbound_2, outbound_scandate_2,
               flag_created, flag_pickup, flag_arrival, flag_inbound, flag_outbound,
               op_date_pickup, op_date_inbound_effective
        FROM enriched.dispatch_enriched
        WHERE operation_date_created = %s
           OR operation_date_inbound = %s
           OR operation_date_inbound_2 = %s
    """, (d_str, d_str, d_str))

    cols = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    df_day = pd.DataFrame(rows, columns=cols).fillna('')

    print(f"   📊 Query PostgreSQL tổng hợp ngày {d_str}: {len(df_day):,} vận đơn")

    # Aggregate JSON Snapshot
    inbound_group = {}
    outbound_group = {}
    heatmap = {f"{h:02d}:00": 0 for h in range(24)}
    summary = {"total_inbound": 0, "total_outbound": 0, "total_pickup": 0,
               "total_created": 0, "total_rebound": 0, "rot_hom_truoc": 0, "rot_hom_nay": 0}

    for _, r in df_day.iterrows():
        sc_raw   = str(r.get('dispatch_code', '')).strip().upper()
        next_st  = str(r.get('next_station', '')).strip()
        mapped   = dict_station.get(sc_raw, '')
        station  = mapped or (next_st if next_st and next_st != 'KHONG VUNG KHAC' else 'KHONG VUNG KHAC')
        zone     = ZONE_MAP.get(dict_zone.get(sc_raw, '3'), '3')
        area_id  = dict_area.get(sc_raw, 'C01')
        cap      = 1400 if area_id == 'A06' else 780

        wt_kg    = float(r.get('orders_weight') or 0)
        cr_t     = clean_ts_str(r.get('created_time'))
        pk_t     = clean_ts_str(r.get('pickup_time'))
        inb_t    = clean_ts_str(r.get('inbound_scandate'))
        outb_t   = clean_ts_str(r.get('outbound_scandate'))
        arr_t    = clean_ts_str(r.get('arrival_scandate'))
        trip     = str(r.get('trip_code', '')).strip()
        is_reb   = int(r.get('is_rebound') or 0)
        ret_cnt  = int(r.get('return_count') or 0)
        inb_t_2  = clean_ts_str(r.get('inbound_scandate_2'))
        outb_t_2 = clean_ts_str(r.get('outbound_scandate_2'))
        op_inb_2 = str(r.get('operation_date_inbound_2') or '')[:10]

        has_in   = int(r.get('flag_inbound') or 0) == 1
        has_out  = int(r.get('flag_outbound') or 0) == 1
        has_arr  = int(r.get('flag_arrival') or 0) == 1
        has_pick = int(r.get('flag_pickup') or 0) == 1

        op_inb   = str(r.get('op_date_inbound_effective') or r.get('operation_date_inbound') or '')[:10]
        op_fc    = get_op_date(cr_t)
        op_pick  = str(r.get('op_date_pickup') or '')[:10] or get_op_date(pk_t)
        op_arr   = get_op_date(arr_t)
        op_outb  = get_op_date(outb_t)

        fin_op_inb  = op_inb_2 if (is_reb and op_inb_2) else (op_inb if inb_t else '')
        fin_inb_hour= inb_t_2[11:16] if (is_reb and len(inb_t_2) >= 16) else (inb_t[11:16] if len(inb_t) >= 16 else '')
        cr_hour     = cr_t[11:16] if len(cr_t) >= 16 else ''
        pk_hour     = pk_t[11:16] if len(pk_t) >= 16 else ''
        arr_hour    = arr_t[11:16] if len(arr_t) >= 16 else ''

        if has_in or (is_reb and inb_t_2): summary["total_inbound"] += 1
        if has_out or outb_t_2:            summary["total_outbound"] += 1
        if has_pick:                       summary["total_pickup"] += 1
        if not has_pick:                   summary["total_created"] += 1
        if is_reb:                         summary["total_rebound"] += 1

        # Rot flag (theo tiêu chí USER: đơn chưa về HUB, trừ Đã hủy)
        stn_raw = str(r.get('status_sys', '')).strip()
        is_canceled = (stn_raw == 'Đã hủy')
        op_cr_date = str(r.get('operation_date_created') or '')[:10] or op_fc
        drop_type = ''
        if not has_in and not has_arr and not is_canceled:
            if op_cr_date == d_str:
                summary["rot_hom_nay"] += 1
                drop_type = 'rot_today'
            elif op_cr_date and op_cr_date < d_str:
                summary["rot_hom_truoc"] += 1
                drop_type = 'rot_yesterday'

        # Inbound group
        in_status = ('Inbound' if (has_in or is_reb) else 'Transporting' if has_arr else 'Pickup Done' if has_pick else 'Created')
        k_inb = (station, in_status, fin_op_inb, op_fc, op_pick, op_arr, fin_inb_hour, cr_hour, pk_hour, arr_hour, drop_type, trip, is_reb, ret_cnt)
        if k_inb not in inbound_group:
            inbound_group[k_inb] = {'volume': 0, 'weight_kg': 0.0}
        inbound_group[k_inb]['volume'] += 1
        inbound_group[k_inb]['weight_kg'] += wt_kg

        # Outbound group
        if has_out and op_outb == d_str:
            k_outb = (zone, area_id, station)
            if k_outb not in outbound_group:
                outbound_group[k_outb] = {'volume': 0, 'weight_kg': 0.0, 'capacity': cap}
            outbound_group[k_outb]['volume'] += 1
            outbound_group[k_outb]['weight_kg'] += wt_kg

        # Heatmap
        if fin_inb_hour and (fin_op_inb == d_str or op_inb == d_str):
            h_slot = fin_inb_hour[:2] + ":00"
            if h_slot in heatmap:
                heatmap[h_slot] += 1

    inbound_json = [
        {"station_name": k[0], "status": k[1], "volume": v["volume"], "weight_ton": round(v["weight_kg"]/1000.0, 4),
         "op_date_inbound": k[2], "op_date_forecast": k[3], "op_date_pickup": k[4], "op_date_arrival": k[5],
         "inbound_hour": k[6], "created_hour": k[7], "pickup_hour": k[8], "arrival_hour": k[9],
         "drop_type": k[10], "trip_code": k[11], "is_rebound": k[12], "return_count": k[13]}
        for k, v in inbound_group.items()
    ]
    outbound_json = [
        {"zone": k[0], "area_id": k[1], "station_name": k[2], "volume": v["volume"], "weight_ton": round(v["weight_kg"]/1000.0, 4), "capacity": v["capacity"]}
        for k, v in outbound_group.items()
    ]

    snapshot_obj = {
        "snapshot_date": d_str,
        "snapped_at":    now_vn.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "summary":       summary,
        "heatmap":       heatmap,
        "inbound":       inbound_json,
        "outbound":      outbound_json,
        "inventory":     []  # Realtime backlog ignore theo chỉ thị USER
    }

    # Ghi snapshot JSON
    hist_file = os.path.join(HIST_DIR, f"{d_str}.json")
    with open(hist_file, 'w', encoding='utf-8') as f:
        json.dump(snapshot_obj, f, ensure_ascii=False, separators=(',', ':'))
    size_kb = os.path.getsize(hist_file) / 1024
    print(f"   💾 Ghi file snapshot: data/history/{d_str}.json ({size_kb:.1f} KB)")

    # Update history_index.json
    idx = {"available_dates": []}
    if os.path.exists(IDX_FILE):
        try:
            with open(IDX_FILE, encoding='utf-8') as f:
                idx = json.load(f)
        except Exception:
            pass
    if d_str not in idx.get("available_dates", []):
        idx["available_dates"].append(d_str)
        idx["available_dates"].sort(reverse=True)
    with open(IDX_FILE, 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)

    # 5. Upsert vào reporting.kpi_daily
    rate = round(summary['total_outbound'] / summary['total_inbound'] * 100, 2) if summary['total_inbound'] > 0 else 0
    cur.execute("""
        INSERT INTO reporting.kpi_daily
            (op_date, total_inbound, total_outbound, total_pickup, total_created, total_rebound,
             rot_hom_truoc, rot_hom_nay, total_backlog, outbound_rate, record_type, snapped_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'snapshot', NOW())
        ON CONFLICT (op_date) DO UPDATE SET
            total_inbound  = EXCLUDED.total_inbound,
            total_outbound = EXCLUDED.total_outbound,
            total_pickup   = EXCLUDED.total_pickup,
            total_created  = EXCLUDED.total_created,
            total_rebound  = EXCLUDED.total_rebound,
            rot_hom_truoc  = EXCLUDED.rot_hom_truoc,
            rot_hom_nay    = EXCLUDED.rot_hom_nay,
            outbound_rate  = EXCLUDED.outbound_rate,
            record_type    = 'snapshot',
            snapped_at     = NOW();
    """, (d_str, summary['total_inbound'], summary['total_outbound'], summary['total_pickup'],
          summary['total_created'], summary['total_rebound'], summary['rot_hom_truoc'],
          summary['rot_hom_nay'], 0, rate))
    conn.commit()
    conn.close()

    # 6. Git push riêng file history của ngày d_str
    try:
        subprocess.run(["git", "add", f"data/history/{d_str}.json", "data/history_index.json"],
                       cwd=BASE_DIR, capture_output=True, text=True, timeout=30)
        msg = f"chore(history): snapshot {d_str} — Inbound: {summary['total_inbound']:,}, Outbound: {summary['total_outbound']:,}, Rớt: {summary['rot_hom_nay']:,}"
        subprocess.run(["git", "commit", "-m", msg], cwd=BASE_DIR, capture_output=True, text=True, timeout=30)
        push_res = subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, capture_output=True, text=True, timeout=60)
        if push_res.returncode == 0:
            print(f"   🚀 Git Push thành công -> data/history/{d_str}.json đã lên GitHub!")
        else:
            print(f"   ⚠️  Git Push warning: {push_res.stderr.strip()[:100]}")
    except Exception as e_push:
        print(f"   ⚠️  Git Push error: {e_push}")

    print(f"\n✅ [KẾT QUẢ NGÀY {d_str}]")
    print(f"   - Tổng đơn kéo từ JFS API : {len(recs):,} đơn")
    print(f"   - Total Inbound          : {summary['total_inbound']:,}")
    print(f"   - Total Outbound         : {summary['total_outbound']:,}")
    print(f"   - Total Pickup           : {summary['total_pickup']:,}")
    print(f"   - Rớt Hôm Nay (`rot_H`)   : {summary['rot_hom_nay']:,}")
    print(f"   - Rớt Hôm Trước (`rot_T`) : {summary['rot_hom_truoc']:,}")
    print(f"   - File snapshot JSON     : data/history/{d_str}.json ({size_kb:.1f} KB)")


# === LOOP CHẠY TỪNG NGÀY ===
for d_str in dates:
    try:
        process_single_date(d_str)
        time.sleep(1)  # NGHỈ 1 giây giữa các ngày để tránh quá tải API
    except Exception as e_date:
        print(f"\n❌ [LỖI GIAI ĐOẠN NGÀY {d_str}]: {e_date}")
        import traceback
        traceback.print_exc()

print("\n============================================================")
print("🎉 TOÀN BỘ LUỒNG KÉO DỮ LIỆU TỪ 2026-06-30 ĐẾN NAY ĐÃ HOÀN THÀNH!")
print("============================================================")
