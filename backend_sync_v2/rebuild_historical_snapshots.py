import os, sys, json, datetime
from zoneinfo import ZoneInfo
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from sync_postgre import get_pg_conn, get_op_date, clean_ts_str

print("=== REBUILD HISTORICAL SNAPSHOTS (JULY 5 -> AUGUST 3, 2026) ===")

def load_all_orders():
    print("Fetching master orders dataset from PostgreSQL...")
    conn = get_pg_conn()
    query = "SELECT * FROM enriched.dispatch_enriched"
    df = pd.read_sql(query, conn)
    conn.close()
    print(f"Loaded {len(df):,} total order rows.")
    return df

def safe_op_date(val, ts=""):
    if val is not None and not pd.isna(val):
        s = str(val).strip()
        if s and s.lower() not in ('none', 'nan', 'null', ''):
            return s[:10]
    if ts:
        return get_op_date(ts)
    return ""

def rebuild_history():
    df = load_all_orders()
    
    start_date = datetime.date(2026, 7, 5)
    end_date = datetime.date(2026, 8, 3) # Up to yesterday
    
    curr = start_date
    date_list = []
    while curr <= end_date:
        date_list.append(curr.strftime('%Y-%m-%d'))
        curr += datetime.timedelta(days=1)
        
    print(f"Rebuilding {len(date_list)} historical dates: {date_list[0]} to {date_list[-1]}...")
    
    print("Pre-parsing order operating dates with safe null handling...")
    parsed_records = []
    for idx, r in df.iterrows():
        cr_t  = clean_ts_str(r.get('created_time'))
        pk_t  = clean_ts_str(r.get('pickup_time'))
        arr_t = clean_ts_str(r.get('arrival_scandate'))
        inb_t = clean_ts_str(r.get('inbound_scandate'))
        outb_t= clean_ts_str(r.get('outbound_scandate'))
        
        inb_t_2 = clean_ts_str(r.get('inbound_scandate_2'))
        outb_t_2= clean_ts_str(r.get('outbound_scandate_2'))
        is_reb  = int(r.get('is_rebound') or 0)
        
        op_fc   = safe_op_date(r.get('operation_date_created'), cr_t)
        op_pick = safe_op_date(r.get('op_date_pickup'), pk_t)
        op_arr  = safe_op_date(None, arr_t)
        op_inb  = safe_op_date(r.get('op_date_inbound_effective') or r.get('operation_date_inbound'), inb_t)
        op_outb = safe_op_date(r.get('operation_date_inbound_2'), outb_t_2 if is_reb else outb_t)
        
        stn = str(r.get('status_sys') or '').strip()
        is_canceled = (stn == 'Đã hủy')
        
        raw_wt = float(r.get('orders_weight') or 0)
        wt_kg  = (raw_wt / 1000.0) if raw_wt > 5000.0 else raw_wt
        
        pk_st_raw = str(r.get('pickup_station', '')).strip()
        target_st = str(r.get('target_station_name') or r.get('pickup_station2') or '').strip()
        st        = target_st or pk_st_raw or 'BN HUB'
        
        code_val = str(r.get('tracking') or '').strip()
        if not code_val:
            code_val = str(r.get('dispatch_code') or '').strip()
        if not code_val:
            code_val = f"row_{idx}"
            
        parsed_records.append({
            'code': code_val,
            'op_fc': op_fc,
            'op_pick': op_pick,
            'op_arr': op_arr,
            'op_inb': op_inb,
            'op_outb': op_outb,
            'cr_t': cr_t,
            'pk_t': pk_t,
            'arr_t': arr_t,
            'inb_t': inb_t,
            'outb_t': outb_t,
            'inb_t_2': inb_t_2,
            'outb_t_2': outb_t_2,
            'has_in': bool(inb_t or op_inb),
            'has_out': bool(outb_t_2 if is_reb else outb_t),
            'is_reb': is_reb,
            'is_canceled': is_canceled,
            'wt_kg': wt_kg,
            'st': st,
            'pk_st': pk_st_raw,
            'trip': str(r.get('trip_code', '')).strip(),
            'transp_t': clean_ts_str(r.get('transporing_time')),
            'transpd_t': clean_ts_str(r.get('transported_time')),
            'ret_cnt': int(r.get('return_count') or 0),
            'rk': str(r.get('rank') or '').upper(),
            'rd': str(r.get('round') or '').upper(),
            'next_st': str(r.get('next_station') or '').upper(),
        })
        
    records_df = pd.DataFrame(parsed_records)
    print(f"Parsed {len(records_df):,} records ready.")
    
    # Process each historical operating date
    for op_d in date_list:
        # All orders operated/manipulated on op_d (Created, Pickup, Arrival, or Inbounded on op_d)
        mask_ops_today = (records_df['op_fc'] == op_d) | (records_df['op_pick'] == op_d) | (records_df['op_arr'] == op_d) | (records_df['op_inb'] == op_d)
        ops_today = records_df[mask_ops_today]
        
        # Backlog 06:00 AM: Đơn từ các ngày cũ (op_fc < op_d hoặc op_pick < op_d) mà chưa Inbound và chưa Outbound trước mốc op_d
        mask_backlog = (
            ((records_df['op_fc'] < op_d) & (records_df['op_fc'] != '')) |
            ((records_df['op_pick'] < op_d) & (records_df['op_pick'] != ''))
        ) & (~records_df['has_in']) & (~records_df['has_out']) & (~records_df['is_canceled'])
        
        backlog_df = records_df[mask_backlog]
        
        # Combine to get Total Forecast Workload Target for op_d
        workload_df = pd.concat([ops_today, backlog_df]).drop_duplicates(subset=['code'])
        forecast_total = len(workload_df)
        forecast_weight_ton = round(workload_df['wt_kg'].sum() / 1000.0, 3)
        
        # Inbound actuals for op_d
        inbound_df = records_df[(records_df['op_inb'] == op_d) & (~records_df['is_canceled'])]
        inbound_total = len(inbound_df)
        inbound_weight_ton = round(inbound_df['wt_kg'].sum() / 1000.0, 3)
        
        # Breakdown Shuttle vs Linehaul
        is_linehaul = workload_df['st'].str.startswith(('HN ', 'HD ', 'HY ')) | workload_df['pk_st'].str.startswith(('HN ', 'HD ', 'HY ')) | (workload_df['st'] == 'BN HUB') | (workload_df['rk'] == 'BN HUB')
        linehaul_df = workload_df[is_linehaul]
        shuttle_df  = workload_df[~is_linehaul]
        
        shuttle_count  = len(shuttle_df)
        linehaul_count = len(linehaul_df)
        shuttle_weight = round(shuttle_df['wt_kg'].sum() / 1000.0, 3)
        linehaul_weight= round(linehaul_df['wt_kg'].sum() / 1000.0, 3)
        
        kpi_summary = {
            "op_date": op_d,
            "contract_version": "2.0.0",
            "inbound_orders": inbound_total,
            "inbound_weight_ton": inbound_weight_ton,
            "forecast_total": forecast_total,
            "forecast_weight_ton": forecast_weight_ton,
            "shuttle": shuttle_count,
            "shuttle_weight": shuttle_weight,
            "linehaul": linehaul_count,
            "linehaul_weight": linehaul_weight,
            "rot_hom_truoc": len(backlog_df),
            "rot_hom_nay": len(ops_today),
            "linehaul_bn_hub": linehaul_count
        }
        
        hist_dir = os.path.join(PROJECT_ROOT, "data", "history", op_d)
        os.makedirs(hist_dir, exist_ok=True)
        
        kpi_path = os.path.join(hist_dir, "inbound_kpi_summary.json")
        with open(kpi_path, 'w', encoding='utf-8') as f:
            json.dump(kpi_summary, f, ensure_ascii=False, indent=2)
            
        public_hist_dir = os.path.join(PROJECT_ROOT, "public", "data", "history", op_d)
        os.makedirs(public_hist_dir, exist_ok=True)
        with open(os.path.join(public_hist_dir, "inbound_kpi_summary.json"), 'w', encoding='utf-8') as f:
            json.dump(kpi_summary, f, ensure_ascii=False, indent=2)
            
        print(f"  ✓ {op_d}: Forecast={forecast_total:,} | Inbound={inbound_total:,} | Backlog06AM={len(backlog_df):,}")

    print("\n✅ All historical dates successfully rebuilt and frozen!")

if __name__ == '__main__':
    rebuild_history()
