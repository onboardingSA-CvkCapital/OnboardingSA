import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1lr6iS-d_HpYrh1HHe9fjNQhaBugRMsGfpZw-IsPZfV0"
WORKSHEET = "Jobs"
CREDENTIALS_FILE = "credentials.json"

COLUMNS = ["id","job_title","employer","category","province","location","employment_type",
           "salary","posted_date","closing_date","reference_no","about_role",
           "responsibilities","requirements","official_apply_url","source_url","featured","status"]

def _sheet():
    creds = Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET)

def existing_refs():
    ws = _sheet()
    try:
        col = COLUMNS.index("reference_no") + 1
        vals = ws.col_values(col)[1:]
        return set(v.strip().lower() for v in vals if v.strip())
    except Exception:
        return set()

MAXCELL = 45000
def append_jobs(rows):
    if not rows:
        return 0
    for r in rows:
        for k,v in list(r.items()):
            if isinstance(v,str) and len(v)>MAXCELL: r[k]=v[:MAXCELL]
    ws = _sheet()
    data = [[r.get(c, "") for c in COLUMNS] for r in rows]
    ws.append_rows(data, value_input_option="RAW")
    return len(rows)
