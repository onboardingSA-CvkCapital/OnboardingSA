import json, sys, csv, io, datetime, urllib.request

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
        r["id"]=stable_id(r.get("reference_no",""), title, r.get("employer",""))
        out.append(r)
    with open("jobs.json","w",encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",",":"))
    print(f"Wrote jobs.json with {len(out)} live jobs (from CSV).", file=sys.stderr)

if __name__=="__main__":
    main()
