"""scrape_smartrecruiters.py  -  OnboardingSA

Company careers sites on SmartRecruiters, e.g. Standard Bank Group:
  list:   GET https://api.smartrecruiters.com/v1/companies/{company}/postings?country=za&limit=100&offset=N
  advert: GET https://api.smartrecruiters.com/v1/companies/{company}/postings/{id}
          -> jobAd.sections: jobDescription / qualifications / additionalInformation (company text is skipped)
Only South African posts. Fixed rules, no AI. Never fails the daily run.
Usage:  python scrape_smartrecruiters.py [--dry-run]
"""
import re, sys, json, time, argparse, datetime

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
API = "https://api.smartrecruiters.com/v1/companies/{company}/postings"

SITES = [
    {"employer": "Standard Bank", "company": "StandardBankGroup", "ref": "SB",
     "skip": r"standard bank group is a leading africa-focused|we.re passionate about creating growth in africa"},
]
REGION = {"GP": "Gauteng", "WC": "Western Cape", "KZN": "KwaZulu-Natal", "NL": "KwaZulu-Natal", "EC": "Eastern Cape",
          "FS": "Free State", "NW": "North West", "NC": "Northern Cape", "LP": "Limpopo", "MP": "Mpumalanga"}


def get(s, url):
    last = None
    for n in range(3):
        try:
            r = s.get(url, timeout=60)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(3 * (n + 1))
    raise RuntimeError(f"{url}: {last}")


def list_jobs(s, cfg):
    out, offset = [], 0
    while offset < 2000:
        d = get(s, API.format(company=cfg["company"]) + f"?country=za&limit=100&offset={offset}")
        items = d.get("content") or []
        out += items
        offset += 100
        if not items or offset >= (d.get("totalFound") or 0):
            break
    return out


def build_row(cfg, j, columns):
    from sa_places import province_of
    from scrape_dpsa import guess_category
    from advert_sections import sections, lines_of
    sec = (j.get("jobAd") or {}).get("sections") or {}
    txt = lambda k: (sec.get(k) or {}).get("text") or ""
    skip = re.compile(cfg["skip"], re.I)
    jd = txt("jobDescription")
    about, resp, req0 = sections(jd, skip)
    if not resp:                                     # description is usually one purpose paragraph (+ maybe a list)
        lines = [t for t, _ in lines_of(jd) if not skip.search(t)]
        items = re.findall(r"<li\b[^>]*>(.*?)</li>", jd, re.S | re.I)
        if items:
            resp = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).strip() for x in items]
            about = [l for l in lines if l not in resp]
        else:
            about = lines
    _, r2, req = sections("<p><b>Requirements</b></p>" + txt("qualifications") + txt("additionalInformation"), skip)
    req = req0 + r2 + req if not req0 else req0 + req
    title = re.sub(r"\s+", " ", j.get("name") or "").strip()
    loc = j.get("location") or {}
    city = (loc.get("city") or "").strip()
    province = REGION.get((loc.get("region") or "").upper(), "") or province_of(city)
    place = ", ".join(x for x in (city, province) if x)
    te = ((j.get("typeOfEmployment") or {}).get("label") or "")
    typ = ("Internship" if re.search(r"intern|graduate|learnership|bursar|apprentice|trainee", title, re.I) else
           "Contract" if re.search(r"contract|temporary|fixed", te + " " + title, re.I) else
           "Part-time" if "part" in te.lower() else "Full-time")
    art = "an" if re.match(r"[AEIOU]", title) else "a"
    intro = f"{cfg['employer']} is hiring {art} {title}" + (f", based in {place}" if place else "") + "."
    cat = guess_category(title, cfg["employer"])
    url = j.get("postingUrl") or j.get("applyUrl") or ""
    row = {k: "" for k in columns}
    row.update({
        "job_title": title, "employer": cfg["employer"],
        "category": "" if cat == "Government" else cat,
        "location": city, "province": province,
        "employment_type": typ,
        "posted_date": (j.get("releasedDate") or "")[:10],
        "closing_date": "",
        "reference_no": f"{cfg['ref']}-{j.get('refNumber') or j.get('id')}",
        "about_role": "\n".join([intro] + about[:10]),
        "responsibilities": "\n".join(resp[:80]),
        "requirements": "\n".join(req[:80]),
        "official_apply_url": url, "source_url": url,
        "status": "live",
    })
    return row


def scrape_site(s, cfg, columns):
    items = list_jobs(s, cfg)
    print(f"{cfg['employer']}: {len(items)} South African jobs on SmartRecruiters", file=sys.stderr)
    rows, old = [], (datetime.date.today() - datetime.timedelta(days=120)).isoformat()
    for it in items:
        try:
            j = get(s, API.format(company=cfg["company"]) + "/" + str(it["id"]))
            row = build_row(cfg, j, columns)
            time.sleep(0.3)
        except Exception as e:
            print(f"  skipped {it.get('name')}: {e}", file=sys.stderr)
            continue
        if not row["responsibilities"] and not row["requirements"] and len(row["about_role"].split()) < 70:
            print(f"  skipped (could not read duties/requirements): {row['job_title']}", file=sys.stderr)
            continue
        if row["posted_date"] and row["posted_date"] < old:
            print(f"  skipped (posted {row['posted_date']}, no closing date - stale): {row['job_title']}", file=sys.stderr)
            continue
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    import requests, sheet_writer
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    for cfg in SITES:
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
            new, upd = sheet_writer.upsert_jobs(rows, update_fields=("about_role", "responsibilities", "requirements"))
            gone = sheet_writer.retire_missing(cfg["employer"], {r["reference_no"] for r in rows}) if rows else 0
            print(f"{cfg['employer']}: found {len(rows)}, wrote {new} new, updated {upd}, closed {gone} no longer listed.", file=sys.stderr)
        except Exception as e:
            print(f"{cfg['employer']}: could not save ({e})", file=sys.stderr)


if __name__ == "__main__":
    main()
