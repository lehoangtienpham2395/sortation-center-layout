import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_postgre import get_pg_conn
import pandas as pd

conn = get_pg_conn()

# 1. Backlog source set
df_bl = pd.read_sql("""
    SELECT DISTINCT COALESCE(billcode, bill_no) as billcode FROM kpi_hub.backlog_live
    UNION
    SELECT DISTINCT COALESCE(billcode, bill_no) as billcode FROM kpi_hub.raw_backlog
""", conn)
backlog_set = set(str(x).strip() for x in df_bl['billcode'] if str(x).strip())

# 2. Query dispatch_enriched for active window (last 15 days, un-outbounded)
df_all = pd.read_sql("""
    SELECT 
        tracking,
        status_sys,
        operation_date_created,
        operation_date_inbound,
        inbound_scandate,
        outbound_scandate,
        pickup_station,
        next_station,
        dispatch_code,
        orders_weight
    FROM enriched.dispatch_enriched
    WHERE outbound_scandate IS NULL
      AND operation_date_created::date >= ('2026-08-17'::date - INTERVAL '15 days');
""", conn)

# Classification logic
today = '2026-08-17'
canceled_count = 0
canceled_wt = 0.0
miss_out_count = 0
miss_out_wt = 0.0

bn_total = 0
bn_canceled = 0
bn_canceled_wt = 0.0
bn_miss_out = 0
bn_miss_out_wt = 0.0

for _, row in df_all.iterrows():
    st = str(row['status_sys'] or '').lower()
    is_canc = any(kw in st for kw in ['hủy', 'cancel', 'da huy'])
    
    has_in = bool(row['inbound_scandate'] or row['operation_date_inbound'])
    has_out = bool(row['outbound_scandate'])
    ref_inb_date = str(row['operation_date_inbound'] or row['operation_date_created'])[:10]
    
    is_miss = False
    if not is_canc and has_in and not has_out:
        if ref_inb_date < today and str(row['tracking']).strip() not in backlog_set:
            is_miss = True
            
    # Check BN HUB
    pk = str(row['pickup_station'] or '').strip().upper()
    next_st = str(row['next_station'] or '').strip().upper()
    sc = str(row['dispatch_code'] or '').strip().upper()
    is_bn = (pk != 'BN HUB') and ('BN HUB' in next_st or next_st.startswith(('BN', 'HN', 'HD', 'HY', 'HP', 'QN', 'PT', 'TH', 'NA', 'HT', 'VP', 'BG', 'BK', 'CB', 'LS', 'LC', 'TQ', 'YB', 'SL', 'DB', 'HG', 'ND', 'NB', 'HA')) or (sc and any(sc.startswith(pfx) for pfx in ('HN', 'BN', 'HD', 'HY', 'HP', 'TB', 'QN', 'PT', 'TH', 'NA', 'HT', 'VP', 'BG', 'BK', 'CB', 'LS', 'LC', 'TQ', 'YB', 'SL', 'DB', 'HG', 'ND', 'NB', 'HA')) and not sc.startswith(('TNI', 'TNG'))))

    wt = float(row['orders_weight'] or 0.0) / 1000.0

    if is_canc:
        canceled_count += 1
        canceled_wt += wt
    elif is_miss:
        miss_out_count += 1
        miss_out_wt += wt

    if is_bn:
        bn_total += 1
        if is_canc:
            bn_canceled += 1
            bn_canceled_wt += wt
        elif is_miss:
            bn_miss_out += 1
            bn_miss_out_wt += wt

# Write report
with open('deduction_breakdown_report.md', 'w', encoding='utf-8') as f:
    f.write("# BÁO CÁO CHI TIẾT SỐ LƯỢNG ĐÃ TRỪ (ĐƠN HỦY & MISS OUTBOUND)\n\n")
    
    # Total HUB
    f.write("## 1. TỔNG TOÀN HUB (TẤT CẢ CÁC LUỒNG / TOÀN BỘ FORECAST)\n\n")
    f.write(f"- **Tổng số đơn chưa Outbound trong hệ thống:** {len(df_all):,} đơn\n")
    f.write(f"- ❌ **Số đơn ĐÃ HỦY (Cancelled):** **{canceled_count:,} đơn** ({canceled_wt:,.3f} Tấn)\n")
    f.write(f"- 🚚 **Số đơn MISS OUTBOUND (Đã Inbound ngày cũ, thực tế đã xuất nhưng quên quét Outbound & không còn trong Backlog):** **{miss_out_count:,} đơn** ({miss_out_wt:,.3f} Tấn)\n")
    f.write(f"- 🎯 **Tổng số đơn ảo/rác đã trừ toàn HUB:** **{(canceled_count + miss_out_count):,} đơn** ({(canceled_wt + miss_out_wt):,.3f} Tấn)\n\n")
    
    # BN HUB
    f.write("## 2. RIÊNG LUỒNG BN HUB (LINEHAUL / CHUTE A06)\n\n")
    f.write(f"- **Tổng số đơn BN HUB ban đầu (trước khi lọc):** {bn_total:,} đơn\n")
    f.write(f"- ❌ **Số đơn ĐÃ HỦY (Cancelled) của BN HUB:** **{bn_canceled:,} đơn** ({bn_canceled_wt:,.3f} Tấn)\n")
    f.write(f"- 🚚 **Số đơn MISS OUTBOUND của BN HUB:** **{bn_miss_out:,} đơn** ({bn_miss_out_wt:,.3f} Tấn)\n")
    f.write(f"- 🎯 **Tổng số đơn đã trừ của BN HUB:** **{(bn_canceled + bn_miss_out):,} đơn** ({(bn_canceled_wt + bn_miss_out_wt):,.3f} Tấn)\n")
    f.write(f"- 🏆 **Số đơn BN HUB CHUẨN THỰC TẾ CÒN LẠI:** **{(bn_total - bn_canceled - bn_miss_out):,} đơn**\n")

print("Report generated successfully in deduction_breakdown_report.md")
