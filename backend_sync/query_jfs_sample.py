import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime, timedelta
from pipeline_unified_v6 import (
    build_session, TokenManager, auth_post,
    ACCOUNT, PASSWORD, URL_DISPATCH, cfg, load_json, clean_wb
)

sample_wbs = [
    '530755010201', '530232750201', '530594540201', '530159600201',
    '530474540201', '530297540201', '530297340201'
]

session = build_session()
token_mgr = TokenManager(session, ACCOUNT, PASSWORD, label='CheckSamples')
hdrs = load_json(cfg('dispatchheaders.json'))
base_pl = load_json(cfg('dispatchpayload.json'))

end_dt = datetime.now()
start_dt = end_dt - timedelta(days=15)
base_pl['startInputTime'] = start_dt.strftime('%Y-%m-%d 00:00:00')
base_pl['endInputTime'] = end_dt.strftime('%Y-%m-%d %H:%M:%S')

base_pl['waybillNo'] = ','.join(sample_wbs)
base_pl['billCode'] = ','.join(sample_wbs)
base_pl['current'] = 1
base_pl['size'] = 100

print("Querying JFS with formatted dates for the 7 sample tracking numbers...")
try:
    r = auth_post(session, URL_DISPATCH, token_mgr, hdrs, data=base_pl, label='SampleQuery')
    res = r.json()
    data = res.get('data', {})
    recs = data.get('records', [])
    print(f"Returned {len(recs)} records from JFS:")
    for rec in recs:
        wb = rec.get('waybillNo') or rec.get('waybillId')
        st_name = rec.get('orderStatusName')
        st_code = rec.get('orderStatusCode') or rec.get('orderStatus')
        ct = rec.get('cancelTime')
        cr = rec.get('cancelReason')
        print(f"Tracking: {wb} | orderStatusName: '{st_name}' | code: {st_code} | cancelTime: {ct} | cancelReason: {cr}")
except Exception as e:
    print(f"Error querying JFS: {e}")
