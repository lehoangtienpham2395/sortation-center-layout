import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_unified_v6 import (
    build_session, TokenManager, auth_post,
    ACCOUNT, PASSWORD, URL_DISPATCH, cfg, load_json, clean_wb
)
from sync_postgre import get_pg_conn
from datetime import datetime, timedelta

session = build_session()
token_mgr = TokenManager(session, ACCOUNT, PASSWORD, label='TestDispatchCancels')
hdrs = load_json(cfg('dispatchheaders.json'))
base_pl = load_json(cfg('dispatchpayload.json'))

end_dt = datetime.now()
start_dt = end_dt - timedelta(days=7)
start_str = start_dt.strftime('%Y-%m-%d 00:00:00')
end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')

base_pl['startInputTime'] = start_str
base_pl['endInputTime'] = end_str
base_pl['size'] = 500
base_pl['current'] = 1

print(f"Checking Dispatch status on JFS from {start_str} to {end_str}...")

all_statuses = {}
cancels_found = []

for p in range(1, 15):
    base_pl['current'] = p
    try:
        r = auth_post(session, URL_DISPATCH, token_mgr, hdrs, data=base_pl, label=f'p{p}')
        res = r.json()
        data = res.get('data')
        if isinstance(data, str):
            try: data = json.loads(data)
            except: data = {}
        if not isinstance(data, dict):
            continue
        recs = data.get('records', []) or data.get('list', [])
        if not recs:
            break
            
        for rec in recs:
            st = str(rec.get('orderStatusName') or '')
            ct = str(rec.get('cancelTime') or '')
            cr = str(rec.get('cancelReason') or '')
            wb = clean_wb(rec.get('waybillId') or rec.get('waybillNo') or rec.get('billCode'))
            
            all_statuses[st] = all_statuses.get(st, 0) + 1
            if any(kw in st.lower() for kw in ['hủy', 'cancel', 'da huy']) or (ct and ct != 'None') or (cr and cr != 'None'):
                cancels_found.append((wb, st, ct, cr))
                
        print(f"   p{p}: {len(recs)} records | Cumulative cancels: {len(cancels_found)}")
    except Exception as e:
        print(f"   p{p} error: {e}")

    time.sleep(1.0) # Slow & safe

print("\n--- All Statuses found in sample pages ---")
for k, v in sorted(all_statuses.items(), key=lambda x: x[1], reverse=True):
    print(f"  '{k}': {v}")

print(f"\nTotal cancelled records found in sample: {len(cancels_found)}")
if cancels_found:
    print("Sample cancels:", cancels_found[:5])
