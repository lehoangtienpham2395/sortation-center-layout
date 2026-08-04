"""
snapshot_daily.py — Daily 06:00 AM Historical Snapshot (Write-Once Guard)
==========================================================================
🕕 THỜI ĐIỂM CHẠY: Đúng 06:00 AM VN mỗi ngày (cron: 0 6 * * *)
📦 OUTPUT:  public/data/history/{YESTERDAY}/inbound_kpi_summary.json
🔒 WRITE-ONCE: Nếu file đã tồn tại → SKIP, không bao giờ ghi đè lịch sử
🕐 TIME GUARD: Từ chối chạy nếu ngoài cửa sổ 06:00–09:00 (trừ --force)

Forecast = Tất cả đơn có Created HOẶC Pickup trong ngày vận hành hôm qua
         + Đơn tồn đọng (có Pickup trước hôm qua, chưa Inbound)
"""

import os, sys, io, json, subprocess, datetime, argparse
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sync_postgre import get_pg_conn, get_sa_engine, get_op_date, clean_ts_str
import pandas as pd

# ── Thời gian hiện tại (VN) ──────────────────────────────────────────────────
tz_vn       = ZoneInfo("Asia/Ho_Chi_Minh")
now_vn      = datetime.datetime.now(tz_vn)
SNAP_DATE   = (now_vn - datetime.timedelta(days=1)).strftime("%Y-%m-%d")  # ngày cần chốt

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

PUBLIC_HIST_DIR = os.path.join(PROJECT_ROOT, "public", "data", "history", SNAP_DATE)
PUBLIC_IDX_FILE = os.path.join(PROJECT_ROOT, "public", "data", "history", "history_index.json")

DATA_HIST_DIR   = os.path.join(PROJECT_ROOT, "data", "history", SNAP_DATE)   # mirror (for safety)
KPI_FILE        = os.path.join(PUBLIC_HIST_DIR, "inbound_kpi_summary.json")


# ══════════════════════════════════════════════════════════════════════════════
# GUARD 1: WRITE-ONCE — không bao giờ ghi đè lịch sử đã chốt
# ══════════════════════════════════════════════════════════════════════════════
def check_write_once() -> bool:
    """Trả về True nếu cần SKIP (file đã tồn tại)."""
    if os.path.exists(KPI_FILE):
        print(f"🔒 SKIP — public/data/history/{SNAP_DATE}/inbound_kpi_summary.json đã tồn tại (write-once).")
        return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# GUARD 2: TIME WINDOW — chỉ chạy trong cửa sổ 06:00–09:00 VN
# ══════════════════════════════════════════════════════════════════════════════
def check_time_window(force: bool) -> bool:
    """Trả về True nếu được phép chạy."""
    if force:
        print(f"⚡ --force mode: bỏ qua time-window guard.")
        return True
    hour = now_vn.hour
    if 6 <= hour < 9:
        print(f"✅ Time window OK: {now_vn.strftime('%H:%M')} nằm trong 06:00–09:00.")
        return True
    print(f"⏰ SKIP — Ngoài cửa sổ 06:00–09:00 (hiện tại: {now_vn.strftime('%H:%M')}). Dùng --force để override.")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# COMPUTE: Forecast + Inbound theo 2-logtime rule (giống rebuild script)
# ══════════════════════════════════════════════════════════════════════════════
def compute_kpi(snap_date: str) -> dict:
    """Tính KPI cho snap_date theo 2-logtime rule."""

    print(f"\nQuerying PostgreSQL for ngày vận hành {snap_date}...")
    query = f"""
        SELECT
            COALESCE(tracking, dispatch_code, CAST(ctid AS TEXT)) AS code,
            created_time, pickup_time,
            inbound_scandate, outbound_scandate, arrival_scandate,
            inbound_scandate_2, outbound_scandate_2,
            operation_date_created,
            operation_date_inbound,
            op_date_pickup,
            is_rebound, return_count,
            status_sys,
            orders_weight,
            pickup_station, next_station, rank, round
        FROM enriched.dispatch_enriched
    """
    try:
        sa_engine = get_sa_engine()
        if sa_engine:
            df = pd.read_sql(query, sa_engine)
            sa_engine.dispose()
        else:
            import warnings
            conn = get_pg_conn()
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                df = pd.read_sql(query, conn)
            conn.close()
    except Exception as e:
        print(f"   ❌ Query failed: {e}")
        return {}

    df = df.fillna('')
    print(f"   Loaded {len(df):,} total rows.")

    # ── Parse mỗi đơn ─────────────────────────────────────────────────────
    records = []
    for _, r in df.iterrows():
        cr_t   = clean_ts_str(r.get('created_time'))
        pk_t   = clean_ts_str(r.get('pickup_time'))
        inb_t  = clean_ts_str(r.get('inbound_scandate'))
        outb_t = clean_ts_str(r.get('outbound_scandate'))
        inb_t2 = clean_ts_str(r.get('inbound_scandate_2'))
        outb_t2= clean_ts_str(r.get('outbound_scandate_2'))
        is_reb = int(r.get('is_rebound') or 0)

        stn = str(r.get('status_sys') or '').strip()
        is_canceled = (stn == 'Đã hủy')
        if is_canceled:
            continue

        # Operating dates (2-logtime rule: chỉ dùng created & pickup)
        op_fc   = str(r.get('operation_date_created') or '')[:10] or get_op_date(cr_t)
        op_pick = str(r.get('op_date_pickup') or '')[:10] or get_op_date(pk_t)
        op_inb  = str(r.get('operation_date_inbound') or '')[:10] or get_op_date(inb_t)

        has_in  = bool(inb_t or op_inb)
        has_out = bool(outb_t2 if is_reb else outb_t)

        wt_kg   = float(r.get('orders_weight') or 0)
        if wt_kg > 5000.0:
            wt_kg /= 1000.0   # đổi gram → kg

        pk_st  = str(r.get('pickup_station') or '').strip()
        nxt_st = str(r.get('next_station') or '').upper()
        rk_val = str(r.get('rank') or '').upper()
        rd_val = str(r.get('round') or '').upper()
        is_north = (
            pk_st.startswith(('BN HUB', 'HN ', 'HD ', 'HY ')) or
            nxt_st.startswith(('BN HUB', 'HN ', 'HD ', 'HY ')) or
            rk_val == 'BN HUB' or 'LINEHAUL' in rd_val
        )

        records.append({
            'op_fc': op_fc,
            'op_pick': op_pick,
            'op_inb': op_inb,
            'has_in': has_in,
            'has_out': has_out,
            'wt_kg': wt_kg,
            'is_north': is_north,
            'pk_st': pk_st,
        })

    rdf = pd.DataFrame(records)
    print(f"   Parsed {len(rdf):,} valid records.")

    # ── Forecast: ops_today (created OR pickup on snap_date) + backlog 06AM ─
    mask_ops = (rdf['op_fc'] == snap_date) | (rdf['op_pick'] == snap_date)
    ops_today = rdf[mask_ops].drop_duplicates()

    mask_backlog = (
        ((rdf['op_fc'] < snap_date) & (rdf['op_fc'] != '')) |
        ((rdf['op_pick'] < snap_date) & (rdf['op_pick'] != ''))
    ) & (~rdf['has_in']) & (~rdf['has_out'])
    backlog_df = rdf[mask_backlog].drop_duplicates()

    workload_df     = pd.concat([ops_today, backlog_df]).drop_duplicates()
    forecast_total  = len(workload_df)
    forecast_weight = round(workload_df['wt_kg'].sum() / 1000.0, 3)

    # ── Inbound actuals ───────────────────────────────────────────────────
    inbound_df      = rdf[rdf['op_inb'] == snap_date]
    inbound_total   = len(inbound_df)
    inbound_weight  = round(inbound_df['wt_kg'].sum() / 1000.0, 3)

    # ── Shuttle vs Linehaul ───────────────────────────────────────────────
    if len(workload_df):
        is_lh       = workload_df['is_north'] == True
        linehaul_df = workload_df[is_lh]
        shuttle_df  = workload_df[~is_lh]
    else:
        linehaul_df = shuttle_df = pd.DataFrame()

    return {
        "op_date":            snap_date,
        "contract_version":   "2.0.0",
        "inbound_orders":     inbound_total,
        "inbound_weight_ton": inbound_weight,
        "forecast_total":     forecast_total,
        "forecast_weight_ton":forecast_weight,
        "shuttle":            len(shuttle_df),
        "shuttle_weight":     round(shuttle_df['wt_kg'].sum() / 1000.0, 3) if len(shuttle_df) else 0,
        "linehaul":           len(linehaul_df),
        "linehaul_weight":    round(linehaul_df['wt_kg'].sum() / 1000.0, 3) if len(linehaul_df) else 0,
        "rot_hom_truoc":      len(backlog_df),
        "rot_hom_nay":        len(ops_today),
        "linehaul_bn_hub":    len(linehaul_df),
        "snapped_at":         now_vn.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def run_snapshot(force: bool = False):
    print(f"\n{'='*60}")
    print(f"SNAPSHOT DAILY — {SNAP_DATE}  ({now_vn.strftime('%H:%M:%S %d/%m/%Y')})")
    print(f"{'='*60}")

    # Guard 1: Time window
    if not check_time_window(force):
        return

    # Guard 2: Write-once
    if check_write_once():
        return

    # Compute KPI
    kpi = compute_kpi(SNAP_DATE)
    if not kpi:
        print("❌ Không có dữ liệu KPI — abort.")
        return

    # Write to public/data/history/{SNAP_DATE}/inbound_kpi_summary.json
    os.makedirs(PUBLIC_HIST_DIR, exist_ok=True)
    with open(KPI_FILE, 'w', encoding='utf-8') as f:
        json.dump(kpi, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Written: public/data/history/{SNAP_DATE}/inbound_kpi_summary.json")
    print(f"   Forecast={kpi['forecast_total']:,} | Inbound={kpi['inbound_orders']:,}")
    print(f"   Shuttle={kpi['shuttle']:,} | Linehaul={kpi['linehaul']:,}")

    # Mirror to data/history/ (backup)
    os.makedirs(DATA_HIST_DIR, exist_ok=True)
    with open(os.path.join(DATA_HIST_DIR, "inbound_kpi_summary.json"), 'w', encoding='utf-8') as f:
        json.dump(kpi, f, ensure_ascii=False, indent=2)

    # Rebuild history_index.json
    print("\nRebuilding history_index.json...")
    try:
        idx_script = os.path.join(SCRIPT_DIR, "build_history_index.py")
        result = subprocess.run(
            [sys.executable, idx_script],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print(f"   ✅ history_index.json updated")
        else:
            print(f"   ⚠️ build_history_index.py error: {result.stderr[:200]}")
    except Exception as e:
        print(f"   ⚠️ build_history_index.py failed: {e}")

    # Git push
    print("\nGit push history snapshot...")
    try:
        subprocess.run(
            ["git", "add",
             f"public/data/history/{SNAP_DATE}",
             "public/data/history/history_index.json"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT, capture_output=True, text=True
        )
        if not status.stdout.strip():
            print("   No changes to commit")
            return
        msg = f"chore(history): snapshot {SNAP_DATE} — {kpi['forecast_total']:,} forecast, {kpi['inbound_orders']:,} inbound"
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30
        )
        push = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60
        )
        if push.returncode == 0:
            print(f"   ✅ Git push OK — public/data/history/{SNAP_DATE}/ live!")
        else:
            print(f"   ❌ Git push failed: {push.stderr.strip()[:200]}")
    except Exception as e:
        print(f"   Git error: {e}")

    print(f"\n🎉 SNAPSHOT {SNAP_DATE} DONE!")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Daily 06:00 AM Historical Snapshot')
    parser.add_argument('--force', action='store_true',
                        help='Bỏ qua time-window guard (06:00-09:00), chạy bất kỳ lúc nào')
    args = parser.parse_args()
    run_snapshot(force=args.force)
