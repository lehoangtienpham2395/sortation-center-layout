import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_unified_v6 import (
    build_session, TokenManager, auth_post,
    ACCOUNT, PASSWORD, URL_DISPATCH, cfg, load_json, clean_wb
)
from sync_postgre import get_pg_conn
from datetime import datetime, timedelta

session = build_session()
token_mgr = TokenManager(session, ACCOUNT, PASSWORD, label='TestDispatch')
hdrs = load_json(cfg('dispatchheaders.json'))
base_pl = load_json(cfg('dispatchpayload.json'))

end_dt = datetime.now()
start_dt = end_dt - timedelta(days=15)
start_str = start_dt.strftime('%Y-%m-%d 00:00:00')
end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')

base_pl['startInputTime'] = start_str
base_pl['endInputTime'] = end_str
base_pl['size'] = 100
base_pl['current'] = 1

print(f"Testing JFS Dispatch API from {start_str} to {end_str}...")

try:
    r = auth_post(session, URL_DISPATCH, token_mgr, hdrs, data=base_pl, label='TestDispatch')
    res = r.json()
    data = res.get('data', {})
    tot = data.get('total')
    recs = data.get('records', [])
    print(f"Total dispatch records available: {tot}")
    print(f"Page 1 records returned: {len(recs)}")
    
    if recs:
        print("\nSample record keys:", list(recs[0].keys()))
        print("Sample record values:")
        print({k: recs[0][k] for k in ['waybillNo', 'orderStatusName', 'orderStatus', 'pickupStation', 'nextStation', 'createdTime'] if k in recs[0]})
        
except Exception as e:
    print(f"Error testing dispatch: {e}")
