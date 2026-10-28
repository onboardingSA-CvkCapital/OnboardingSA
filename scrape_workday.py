"""scrape_workday.py  -  OnboardingSA

Company careers sites that run on Workday (same layout for every company):
  list:   POST https://{host}/wday/cxs/{tenant}/{site}/jobs     {"limit":20,"offset":N,"searchText":"","appliedFacets":{}}
  advert: GET  https://{host}/wday/cxs/{tenant}/{site}{externalPath}   -> jobPostingInfo
Only South African posts are kept. Fixed rules, no AI. One company failing never stops the others or the daily run.
Usage:  python scrape_workday.py [--dry-run] [--only SAB]
"""
import re, sys, json, time, argparse, datetime

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

SITES = [
    {"employer": "SAB", "host": "wd1.myworkdaysite.com", "tenant": "abinbev", "site": "SAB", "ref": "SAB",
     "public": "https://wd1.myworkdaysite.com/recruiting/abinbev/SAB",
     "skip": r"dreaming big is in our dna|are you ready to join a team that dreams|ab inbev is an equal|"
             r"we look for people with passion"},
    {"employer": "Pick n Pay", "host": "picknpay.wd3.myworkdayjobs.com", "tenant": "picknpay", "site": "PNP_Careers", "ref": "PNP",
     "public": "https://picknpay.wd3.myworkdayjobs.com/PNP_Careers",
     "skip": r"it'?s fun to work in a company|if you like wild growth|discover who we are|"
             r"the incumbent may also be expected to perform other duties"},
]

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}


def http(s, method, url, **kw):
    last = None
    for n in range(3):
        try:
            r = s.request(method, url, timeout=60, **kw)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(3 * (n + 1))
    raise RuntimeError(f"{url}: {last}")


def list_jobs(s, cfg):
    base = f"https://{cfg['host']}/wday/cxs/{cfg['tenant']}/{cfg['site']}"
    out, offset, total = [], 0, None
    while offset < 2000:
        d = http(s, "POST", base + "/jobs", json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": ""})
        posts = d.get("jobPostings") or []
        if total is None:
            total = d.get("total") or 0
        out += posts
        offset += 20
        if not posts or offset >= total:
            break
        time.sleep(0.5)
    return base, out


def closing_from_text(t):
    m = re.search(r"closing date\s*:?\s*(?:[A-Za-z]+day,?\s*)?(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})", t or "", re.I)
    if m and m.group(2).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return ""


def emp_type(time_type, title, text):
    if re.search(r"intern|graduate|learnership|bursar|apprentice|trainee|in-service", title, re.I):
        return "Internship"
    if re.search(r"fixed[- ]term|\bcontract\b|temporary", title + " " + text[:600], re.I):
        return "Contract"
    t = (time_type or "").lower()
    return "Part-time" if "part" in t else "Full-time"


def build_row(cfg, info, columns):
    from sa_places import province_of
    from scrape_dpsa import guess_category
    from advert_sections import sections
    import html as _h
    desc = info.get("jobDescription", "")
    about, resp, req = sections(desc, re.compile(cfg["skip"], re.I))
    title = re.sub(r"^\W+", "", re.sub(r"\s+", " ", info.get("title", ""))).strip()
    loc = re.sub(r"\s+-\s+", ", ", info.get("location") or "").strip()
    loc = re.sub(r"^HQ\s+", "", loc)
    province = province_of(loc)
    plain = _h.unescape(re.sub(r"<[^>]+>", " ", desc))
    closing = info.get("endDate") or closing_from_text(plain)
    art = "an" if re.match(r"[AEIOU]", title) else "a"
    intro = f"{cfg['employer']} is hiring {art} {title}" + (f", based in {loc}" if loc else "") + "."
    cat = guess_category(title, cfg["employer"])
    row = {k: "" for k in columns}
    row.update({
        "job_title": title, "employer": cfg["employer"],
        "category": "" if cat == "Government" else cat,
        "location": loc, "province": province,
        "employment_type": emp_type(info.get("timeType"), title, plain),
        "posted_date": (info.get("startDate") or "")[:10],
        "closing_date": (closing or "")[:10],
        "reference_no": f"{cfg['ref']}-{info.get('jobReqId', '')}",
        "about_role": "\n".join([intro] + (about if not (resp or req) else about[:6])),
        "responsibilities": "\n".join(resp[:80]),
        "requirements": "\n".join(req[:80]),
        "official_apply_url": info.get("externalUrl") or cfg["public"],
        "source_url": info.get("externalUrl") or cfg["public"],
        "status": "live",
    })
    return row


def scrape_site(s, cfg, columns):
    base, posts = list_jobs(s, cfg)
    print(f"{cfg['employer']}: {len(posts)} jobs on Workday", file=sys.stderr)
    rows, today, seen = [], datetime.date.today().isoformat(), set()
    for p in posts:
        try:
            info = http(s, "GET", base + p["externalPath"]).get("jobPostingInfo") or {}
            time.sleep(0.4)
        except Exception as e:
            print(f"  skipped {p.get('title')}: {e}", file=sys.stderr)
            continue
        country = ((info.get("country") or {}).get("descriptor") or "").strip()
        if country and country != "South Africa":
            continue
        if info.get("jobReqId") in seen:
            continue
        seen.add(info.get("jobReqId"))
        row = build_row(cfg, info, columns)
        if not row["responsibilities"] and not row["requirements"] and len(row["about_role"].split()) < 70:
            print(f"  skipped (could not read duties/requirements): {row['job_title']}", file=sys.stderr)
            continue
        if row["closing_date"] and row["closing_date"] < today:
            continue
        old = (datetime.date.today() - datetime.timedelta(days=120)).isoformat()
        if not row["closing_date"] and row["posted_date"] and row["posted_date"] < old:
            print(f"  skipped (posted {row['posted_date']}, no closing date - stale): {row['job_title']}", file=sys.stderr)
            continue
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    import requests, sheet_writer
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"})
    for cfg in SITES:
        if a.only and a.only.lower() not in (cfg["employer"].lower(), cfg["ref"].lower()):
            continue
        try:
            rows = scrape_site(s, cfg, sheet_writer.COLUMNS)
        except Exception as e:
            print(f"{cfg['employer']}: could not read the careers site ({e})", file=sys.stderr)
            continue
        if a.dry_run:
            for r in rows:
                print(json.dumps(r, ensure_ascii=False, indent=1))
            print(f"{cfg['employer']}: {len(rows)} jobs", file=sys.stderr)
            continue
        try:
            new, upd = sheet_writer.upsert_jobs(rows, update_fields=("closing_date", "about_role", "responsibilities", "requirements"))
            gone = sheet_writer.retire_missing(cfg["employer"], {r["reference_no"] for r in rows}) if rows else 0
            print(f"{cfg['employer']}: found {len(rows)}, wrote {new} new, updated {upd}, closed {gone} no longer listed.", file=sys.stderr)
        except Exception as e:
            print(f"{cfg['employer']}: could not save ({e})", file=sys.stderr)


if __name__ == "__main__":
    main()
