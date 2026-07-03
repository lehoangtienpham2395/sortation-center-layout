import os
import json
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1GMgvwa1MIEg0P102MDBcvwJPd-0wAeZh3hewmz_LBQI"

def inspect_sheets():
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        # Thử đọc từ environment variables nếu chạy cục bộ hoặc file config ở local
        print("GOOGLE_SERVICE_ACCOUNT_JSON env var is not set.")
        return
        
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
        gc = gspread.authorize(creds)
        
        spreadsheet = gc.open_by_key(SHEET_ID)
        print(f"Spreadsheet Title: {spreadsheet.title}")
        print("Worksheets present:")
        for sheet in spreadsheet.worksheets():
            print(f" - Name: '{sheet.title}', ID: {sheet.id}, Rows: {sheet.row_count}, Cols: {sheet.col_count}")
            
    except Exception as e:
        print(f"Error inspecting spreadsheet: {e}")

if __name__ == "__main__":
    inspect_sheets()
