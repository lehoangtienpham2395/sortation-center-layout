import sys, os, datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, 'backend_sync')
import pipeline_unified_v6 as pipe

tz_vn   = ZoneInfo('Asia/Ho_Chi_Minh')
now_vn  = datetime.datetime.now(tz_vn)
start_str = (now_vn - datetime.timedelta(days=2)).strftime('%Y-%m-%d 00:00:00')
end_str   = now_vn.strftime('%Y-%m-%d %H:%M:%S')

session_main = pipe.build_session()
tkn_main = pipe.TokenManager(session_main, pipe.ACCOUNT, pipe.PASSWORD, label='660021')
tkn_main.get_token()

dh_headers = pipe.load_json(pipe.cfg('dispatchheaders.json'))
dp_payload = pipe.load_json(pipe.cfg('dispatchpayload.json'))
dp_payload['startInputTime'] = start_str
dp_payload['endInputTime']   = end_str
dp_payload['current']        = '1'
dp_payload['size']           = '500'

recs = pipe.pull_dispatch(session_main, tkn_main, dh_headers, dp_payload, label='Dispatch500')
print('Retrieved dispatch count:', len(recs))

has_pick_time = [r for r in recs if str(r.get('pickTime') or '').strip()]
has_pick_net  = [r for r in recs if str(r.get('pickNetworkName') or '').strip()]
print('Records with pickTime:', len(has_pick_time))
print('Records with pickNetworkName:', len(has_pick_net))

if has_pick_time:
    print('\nSample 5 pickTime values:')
    for r in has_pick_time[:5]:
        wb = r.get('waybillNo') or r.get('waybillId')
        st = r.get('orderStatusName')
        pt = r.get('pickTime')
        pkn = r.get('pickNetworkName')
        print(f"  wb={wb}  status={st}  pickTime={pt}  station={pkn}")
