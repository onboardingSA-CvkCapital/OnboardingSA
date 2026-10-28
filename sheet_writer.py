import re, hashlib, datetime
import gspread
from google.oauth2.service_account import Credentials
import privacy_clean

SPREADSHEET_ID = "1lr6iS-d_HpYrh1HHe9fjNQhaBugRMsGfpZw-IsPZfV0"
WORKSHEET = "Jobs"
CREDENTIALS_FILE = "credentials.json"

COLUMNS = ["id","job_title","employer","category","province","location","employment_type",
           "salary","posted_date","closing_date","reference_no","about_role",
           "responsibilities","requirements","official_apply_url","source_url","featured","status"]

MAXCELL = 45000

def _today():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=2)).date().isoformat()   # SAST

def _sheet():
    creds = Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET)

def _norm(s):
    return re.sub(r'\s+', ' ', (s or "").strip().lower())

def fingerprint(row):
    base = (_norm(row.get("employer")) + "|" + _norm(row.get("job_title")) + "|" + _norm(row.get("location"))
            + "|" + _norm(row.get("reference_no")))
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

def _existing_keys(ws):
    vals = ws.get_all_values()
    if not vals:
        return set(), COLUMNS
    header = vals[0]
    def idx(name):
        return header.index(name) if name in header else -1
    ei, ti, li, ri = idx("employer"), idx("job_title"), idx("location"), idx("reference_no")
    keys = set()
    for r in vals[1:]:
        emp = _norm(r[ei]) if ei>=0 and ei<len(r) else ""
        tit = _norm(r[ti]) if ti>=0 and ti<len(r) else ""
        loc = _norm(r[li]) if li>=0 and li<len(r) else ""
        ref = _norm(r[ri]) if ri>=0 and ri<len(r) else ""
        base = emp + "|" + tit + "|" + loc + "|" + ref
        keys.add(hashlib.sha1(base.encode("utf-8")).hexdigest()[:16])
    return keys, header

def upsert_jobs(rows, update_fields=()):
    """Like append_jobs, but rows already in the sheet get `update_fields` refreshed when they changed
    (e.g. a SAPS apply link that became available, or an extended closing date)."""
    if not rows:
        return 0, 0
    from gspread.utils import rowcol_to_a1
    ws = _sheet()
    vals = ws.get_all_values()
    header = vals[0] if vals else COLUMNS
    col = {name: i for i, name in enumerate(header)}
    where = {}
    for n, r in enumerate(vals[1:], start=2):
        g = lambda name: r[col[name]] if name in col and col[name] < len(r) else ""
        where[fingerprint({"employer": g("employer"), "job_title": g("job_title"),
                           "location": g("location"), "reference_no": g("reference_no")})] = (n, r)
    to_write, updates, touched = [], [], set()
    for r in rows:
        privacy_clean.clean_job(r)
        for k, v in list(r.items()):
            if isinstance(v, str) and len(v) > MAXCELL:
                r[k] = v[:MAXCELL]
        if not r.get("posted_date"):
            r["posted_date"] = _today()      # first day we saw it; Google rejects jobs without datePosted
        fp = fingerprint(r)
        if fp in where:
            n, old = where[fp]
            if "posted_date" in col and n and not (old[col["posted_date"]] if col["posted_date"] < len(old) else "").strip():
                updates.append({"range": rowcol_to_a1(n, col["posted_date"] + 1), "values": [[r["posted_date"]]]})
                touched.add(n)
            for f in update_fields:
                if f in col and (old[col[f]] if col[f] < len(old) else "") != r.get(f, ""):
                    updates.append({"range": rowcol_to_a1(n, col[f] + 1), "values": [[r.get(f, "")]]})
                    touched.add(n)
            continue
        where[fp] = (None, [])
        to_write.append(r)
    if updates:
        ws.batch_update(updates, value_input_option="RAW")
    if to_write:
        ws.append_rows([[r.get(c, "") for c in COLUMNS] for r in to_write], value_input_option="RAW")
    return len(to_write), len(touched)

def existing_refs():
    ws = _sheet()
    try:
        keys, _ = _existing_keys(ws)
        return keys
    except Exception:
        return set()

def append_jobs(rows):
    """Add new jobs; rows already in the sheet are left as they are (except a blank posted_date gets filled)."""
    new, _ = upsert_jobs(rows)
    return new
