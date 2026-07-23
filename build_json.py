import json, sys, datetime
import sheet_writer

LIST_FIELDS = ["id","job_title","employer","category","province","location",
               "employment_type","salary","posted_date","closing_date","featured","status"]

def today():
    return datetime.date.today().isoformat()

def is_expired(closing):
    c = (closing or "").strip()
    if not c:
        return False
    try:
        return c < today()
    except Exception:
        return False

def main():
    ws = sheet_writer._sheet()
    vals = ws.get_all_values()
    if not vals:
        print("Sheet empty.", file=sys.stderr)
        json.dump([], open("jobs.json","w"))
        return
    header = [h.strip() for h in vals[0]]
    idx = {h:i for i,h in enumerate(header)}
    def g(row, key):
        i = idx.get(key, -1)
        return row[i].strip() if 0 <= i < len(row) else ""
    out = []
    for row in vals[1:]:
        status = g(row,"status").lower()
        title = g(row,"job_title")
        closing = g(row,"closing_date")
        if not title or status != "live" or is_expired(closing):
            continue
        rec = {k: g(row,k) for k in LIST_FIELDS}
        out.append(rec)
    with open("jobs.json","w",encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",",":"))
    print(f"Wrote jobs.json with {len(out)} live jobs.", file=sys.stderr)

if __name__ == "__main__":
    main()
