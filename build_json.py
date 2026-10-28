import json, sys, csv, io, datetime, urllib.request
import privacy_clean
from sa_places import province_of
import re as _re

def clean_title(t):
    """Eskom sometimes puts the whole advert header in the title: keep only the job name."""
    t = _re.sub(r"^\s*Position\s*:\s*", "", t or "", flags=_re.I)
    t = _re.split(r"\s+(?:Position\s*/\s*Task Grade|Task Grade|Area of speciali[sz]ation|Job Purpose|Purpose of the job)\b", t, 1, flags=_re.I)[0]
    return t.strip(" :;,-")

def no_dashes(v):
    """Long dashes look machine-written; use 'to' for ranges and a plain hyphen elsewhere."""
    if isinstance(v, str):
        v = v.replace("\ufeff", "").replace("\u200b", "")          # invisible characters some sites leave in
    if not isinstance(v, str) or ("\u2014" not in v and "\u2013" not in v):
        return v
    v = _re.sub(r"(?<=\d)\s*[\u2013\u2014]\s*(?=R?\s?\d)", " to ", v)
    v = _re.sub(r"\s+[\u2013\u2014]\s+", " - ", v)
    return _re.sub(r"[\u2013\u2014]", "-", v)

CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTy-Z3HaB9wPDOljgg7vORWjLhZr-vX8zRUjzsfN972jgdzdnIfFUZqQff2U9bwlv9I4XCnXG1T20xj/pub?output=csv"

def today():
    return datetime.date.today().isoformat()

def is_expired(c):
    c=(c or "").strip()
    if not c: return False
    try: return c < today()
    except Exception: return False

def stable_id(ref, title, employer):
    import re
    r=(ref or "").strip()
    if r: return r
    base=(title or "")+"-"+(employer or "")
    return "job-"+re.sub(r'[^a-z0-9]+','-',base.lower()).strip('-')[:60]

def main():
    req=urllib.request.Request(CSV_URL, headers={"User-Agent":"Mozilla/5.0"})
    raw=urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    reader=csv.DictReader(io.StringIO(raw))
    out=[]
    for row in reader:
        r={(k or "").strip(): (v or "").strip() for k,v in row.items()}
        title=r.get("job_title","")
        status=r.get("status","").lower()
        if not title or status!="live" or is_expired(r.get("closing_date","")):
            continue
        r={k:(v if k in ("official_apply_url","source_url") else no_dashes(v)) for k,v in r.items()}
        r["job_title"]=clean_title(r.get("job_title",""))
        if not r.get("province"):
            r["province"]=province_of(r.get("location",""))   # e.g. Eskom gives only the town
        r["id"]=stable_id(r.get("reference_no",""), title, r.get("employer",""))
        out.append(privacy_clean.clean_job(r))   # never publish personal contact details
    with open("jobs.json","w",encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",",":"))
    print(f"Wrote jobs.json with {len(out)} live jobs (from CSV).", file=sys.stderr)

if __name__=="__main__":
    main()
