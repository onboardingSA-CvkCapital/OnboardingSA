import re, hashlib
import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1lr6iS-d_HpYrh1HHe9fjNQhaBugRMsGfpZw-IsPZfV0"
WORKSHEET = "Jobs"
CREDENTIALS_FILE = "credentials.json"

COLUMNS = ["id","job_title","employer","category","province","location","employment_type",
           "salary","posted_date","closing_date","reference_no","about_role",
           "responsibilities","requirements","official_apply_url","source_url","featured","status"]

MAXCELL = 45000

def _sheet():
    creds = Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET)

def _norm(s):
    return re.sub(r'\s+', ' ', (s or "").strip().lower())

def fingerprint(row):
    base = _norm(row.get("employer")) + "|" + _norm(row.get("job_title")) + "|" + _norm(row.get("location"))
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

def _existing_keys(ws):
    vals = ws.get_all_values()
    if not vals:
        return set(), COLUMNS
    header = vals[0]
    def idx(name):
        return header.index(name) if name in header else -1
    ei, ti, li = idx("employer"), idx("job_title"), idx("location")
    keys = set()
    for r in vals[1:]:
        emp = _norm(r[ei]) if ei>=0 and ei<len(r) else ""
        tit = _norm(r[ti]) if ti>=0 and ti<len(r) else ""
        loc = _norm(r[li]) if li>=0 and li<len(r) else ""
        base = emp + "|" + tit + "|" + loc
        keys.add(hashlib.sha1(base.encode("utf-8")).hexdigest()[:16])
    return keys, header

def existing_refs():
    ws = _sheet()
    try:
        keys, _ = _existing_keys(ws)
        return keys
    except Exception:
        return set()

def append_jobs(rows):
    if not rows:
        return 0
    ws = _sheet()
    existing, _ = _existing_keys(ws)
    to_write = []
    for r in rows:
        for k, v in list(r.items()):
            if isinstance(v, str) and len(v) > MAXCELL:
                r[k] = v[:MAXCELL]
        fp = fingerprint(r)
        if fp in existing:
            continue
        existing.add(fp)
        to_write.append(r)
    if not to_write:
        return 0
    data = [[r.get(c, "") for c in COLUMNS] for r in to_write]
    ws.append_rows(data, value_input_option="RAW")
    return len(to_write)
