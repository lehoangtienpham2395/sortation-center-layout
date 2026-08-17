import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_unified_v6 import (
    build_session, TokenManager, auth_post,
    ACCOUNT, PASSWORD, URL_DISPATCH, cfg, load_json, clean_wb, pull_dispatch
)
from sync_postgre import get_pg_conn
from datetime import datetime, timedelta

session = build_session()
token_mgr = TokenManager(session, ACCOUNT, PASSWORD, label='DispatchPull')
hdrs = load_json(cfg('dispatchheaders.json'))
base_pl = load_json(cfg('dispatchpayload.json'))

end_dt = datetime.now()
start_dt = end_dt - timedelta(days=7)
base_pl['startInputTime'] = start_dt.strftime('%Y-%m-%d 00:00:00')
base_pl['endInputTime'] = end_dt.strftime('%Y-%m-%d %H:%M:%S')
base_pl['size'] = 100
base_pl['current'] = 1

print(f"Calling pull_dispatch with 100 page size slowly...")

all_recs = []
for p in range(1, 10):
    pl = dict(base_pl)
    pl['current'] = str(p)
    try:
        r = auth_post(session, URL_DISPATCH, token_mgr, hdrs, data=pl, label=f'p{p}')
        res = r.json()
        obj = res.get('data')
        if isinstance(obj, dict):
            recs = obj.get('records') or obj.get('list') or obj.get('rows') or []
            all_recs.extend(recs)
            print(f"   p{p}: {len(recs)} records")
            if not recs:
                break
    except Exception as e:
        print(f"   p{p} error: {e}")
        break
    time.sleep(1.0)

print(f"\nTotal pulled: {len(all_recs)}")
statuses = {}
cancels = []
for r in all_recs:
    st = str(r.get('orderStatusName') or '')
    statuses[st] = statuses.get(st, 0) + 1
    wb = clean_wb(r.get('waybillNo') or r.get('waybillId'))
    if any(kw in st.lower() for kw in ['hủy', 'cancel', 'da huy']):
        cancels.append((wb, st))

print("Status distribution:", statuses)
print(f"Cancels found: {len(cancels)}")
