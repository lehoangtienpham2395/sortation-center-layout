import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime, timedelta
from pipeline_unified_v6 import (
    build_session, TokenManager, auth_post,
    ACCOUNT, PASSWORD, URL_DISPATCH, cfg, load_json, clean_wb
)

session = build_session()
token_mgr = TokenManager(session, ACCOUNT, PASSWORD, label='CheckCode104')
hdrs = load_json(cfg('dispatchheaders.json'))
base_pl = load_json(cfg('dispatchpayload.json'))

end_dt = datetime.now()
start_dt = end_dt - timedelta(days=15)
base_pl['startInputTime'] = start_dt.strftime('%Y-%m-%d 00:00:00')
base_pl['endInputTime'] = end_dt.strftime('%Y-%m-%d %H:%M:%S')

# In JFS Dispatch API, what is the parameter name for order status filter?
# Let's test orderStatusCodes or orderStatusCode or orderStatusName
base_pl['orderStatus'] = '104'
base_pl['orderStatusCodes'] = '104'
base_pl['orderStatusCode'] = '104'
base_pl['current'] = '1'
base_pl['size'] = '100'

r = auth_post(session, URL_DISPATCH, token_mgr, hdrs, data=base_pl, label='CancelQuery104')
print("Response JSON:", r.json())
