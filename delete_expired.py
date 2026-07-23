import gspread
from datetime import date
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1lr6iS-d_HpYrh1HHe9fjNQhaBugRMsGfpZw-IsPZfV0"
WORKSHEET = "Jobs"
CREDENTIALS_FILE = "credentials.json"

creds = Credentials.from_service_account_file(
    CREDENTIALS_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets"])
ws = gspread.authorize(creds).open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET)

rows = ws.get_all_values()
header = rows[0]
ci = header.index("closing_date")

today = date.today().isoformat()
keep = [header]
removed = 0
for r in rows[1:]:
    cd = (r[ci] if len(r) > ci else "").strip()
    if cd and cd < today:
        removed += 1
    else:
        keep.append(r)

ws.clear()
ws.update(values=keep, range_name="A1", value_input_option="RAW")
print(f"Deleted {removed} expired jobs. {len(keep)-1} jobs remain.")
