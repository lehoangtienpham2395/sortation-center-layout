import os
import sys
import requests
import json
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

# We import md5 and other helpers from sync_to_sheets to keep it simple
from sync_to_sheets import build_session, TokenManager, auth_post, md5, LOGIN_URL, LOGIN_HEADERS, ACCOUNT, PASSWORD, COUNTRY_ID, URL_SCAN

sys.stdout.reconfigure(encoding='utf-8')

session = build_session()
token_mgr = TokenManager(session, ACCOUNT, PASSWORD, COUNTRY_ID)

# Load payload
base_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(base_dir, 'config', 'inboundheaders.json'), 'r', encoding='utf-8') as f:
    headers = json.load(f)
with open(os.path.join(base_dir, 'config', 'inboundpayload.json'), 'r', encoding='utf-8') as f:
    payload = json.load(f)

# Set date range for yesterday to today
now = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
start_date = (now - timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
end_date = now.strftime('%Y-%m-%d %H:%M:%S')

payload['beginDate'] = start_date
payload['endDate'] = end_date
payload['size'] = 5
payload['current'] = 1

print(f"Logging in and pulling Inbound Scan fields...")
token = token_mgr.get_token()

headers['Authtoken'] = token
headers['authToken'] = token

r = auth_post(session, URL_SCAN, token_mgr, headers, json_body=payload, label='Inbound Scan Inspection')
data_obj = r.json().get('data', {})
records = data_obj.get('records', [])

print(f"Total records found: {data_obj.get('total')}")
if records:
    print("\nKeys in first record:")
    for k, v in records[0].items():
        print(f"  {k}: {v} (Type: {type(v).__name__})")
else:
    print("No records returned.")
