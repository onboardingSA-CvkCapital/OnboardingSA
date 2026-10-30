"""scrape_randwater.py  -  OnboardingSA

Rand Water's own application portal (Graylink eRecruit): https://randwater.erecruit.co/candidateapp/Jobs/Browse
  * the browse page lists job categories with a count; each category page lists its jobs
    (rows link to /candidateapp/Jobs/View/<reference>)
  * a job page is a label/value table: Closing Date, Reference Number, Job Title, Portfolio, Job Type Classification,
    Location (province, town, site), Job Advert Summary, Minimum Requirements, Primary Duties, Knowledge, Skills, Attitude
Fixed rules, no AI. Never fails the daily run.
Usage:  python scrape_randwater.py [--dry-run]
"""
import re, sys, json, html, time, argparse, datetime

BASE = "https://randwater.erecruit.co/candidateapp"
EMPLOYER = "Rand Water"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PROVINCES = {"gauteng": "Gauteng", "mpumalanga": "Mpumalanga", "free state": "Free State", "north west": "North West",
             "limpopo": "Limpopo", "kwazulu-natal": "KwaZulu-Natal", "kwazulu natal": "KwaZulu-Natal",
             "western cape": "Western Cape", "eastern cape": "Eastern Cape", "northern cape": "Northern Cape"}
SKIP = re.compile(r"^all applicants must ensure that applications|^shortlisted applicants will be subjected|"
                  r"^appointments will be made in the context of employment equity", re.I)


def get(s, url):
    last = None
    for n in range(3):
        try:
            r = s.get(url, timeout=60)
            if r.status_code == 200:
                return r.text
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(3 * (n + 1))
    raise RuntimeError(f"{url}: {last}")


def lines(fragment):
    t = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", fragment or "", flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("\xa0", " ").replace("﻿", "")
    out = []
    for l in t.split("\n"):
        l = re.sub(r"^\s*(?:[•·▪◦●\-–*]|\d{1,2}[.)])\s*", "", l).strip()
        l = re.sub(r"\s+", " ", l)
        if l:
            out.append(l)
    return out


def list_jobs(s):
    browse = get(s, BASE + "/Jobs/Browse")
    cats = re.findall(r'href="(/candidateapp/Jobs/Categories/[^"]+)"[^>]*>\s*([^<]*?)\s*\((\d+)\)', browse)
    if not cats:                                       # fall back: every category link, count unknown
        cats = [(u, "", "1") for u in dict.fromkeys(re.findall(r'href="(/candidateapp/Jobs/Categories/[^"]+)"', browse))]
    refs = {}
    for url, _name, count in cats:
        if count == "0":
            continue
        page = get(s, "https://randwater.erecruit.co" + url)
        for row in re.findall(r"<tr class=\"item\"[^>]*Jobs/View/([A-Za-z0-9-]+).*?</tr>", page, re.S):
            refs.setdefault(row, url)
        time.sleep(0.5)
    return list(refs)


def fields(page):
    out = {}
    for label, value in re.findall(r'<td class="label"><span class="item-label">(.*?)</span></td><td class="value">(.*?)</td>', page, re.S):
        out[html.unescape(re.sub(r"<[^>]+>", "", label)).strip().lower()] = value
    return out


def build_row(ref, page, columns):
    from sa_places import province_of
    from scrape_dpsa import guess_category
    f = fields(page)
    one = lambda k: " ".join(lines(f.get(k, ""))).strip()
    title = one("job title")
    if title.isupper():                                  # 'SENIOR ELECTRICAL ENGINEER X3' -> 'Senior Electrical Engineer x3'
        title = re.sub(r"\bX(\d+)\b", r"x\1", title.title())
    town, site = one("location - town / city"), one("location - site")
    province = PROVINCES.get(one("location - province").lower(), "") or province_of(town)
    if re.search(r"services|division|department|office|portfolio", site, re.I):
        site = ""                                        # e.g. 'Scientific Services' is a unit, not a place
    place = ", ".join(x for x in (site if site and site.lower() != town.lower() else "", town) if x)
    closing = ""
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", one("closing date"))
    if m:
        closing = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    summary = [l for l in lines(f.get("job advert summary", "")) if not SKIP.search(l)]
    duties = [l for l in lines(f.get("primary duties", "")) if not SKIP.search(l)]
    req = [l for l in lines(f.get("minimum requirements", "")) if not SKIP.search(l)]
    for k, head in (("knowledge", "Knowledge"), ("skills", "Skills"), ("attitude", "Attitude")):
        extra = lines(f.get(k, ""))
        if extra:
            req += [head + ":"] + extra
    jt = one("job type classification")
    typ = ("Internship" if re.search(r"intern|graduate|learner|bursar|apprentice|trainee", jt + " " + title, re.I) else
           "Contract" if re.search(r"fixed[- ]term|contract|temporary", jt + " " + title, re.I) else
           "Permanent" if "permanent" in jt.lower() else "Full-time")
    portfolio = one("portfolio")
    art = "an" if re.match(r"[AEIOU]", title) else "a"
    lead = (f"Rand Water is offering the {title}" if re.match(r"(graduate )?(internship|learnership|bursary|apprenticeship)|.*programme", title, re.I)
            else f"Rand Water is hiring {art} {title}")
    intro = lead + (f" in {portfolio}" if portfolio else "") + \
            (f", based at {place}" if place else "") + "."
    cat = guess_category(title, EMPLOYER)
    url = f"{BASE}/Jobs/View/{ref}"
    row = {k: "" for k in columns}
    row.update({
        "job_title": title, "employer": EMPLOYER,
        "category": "" if cat == "Government" else cat,
        "location": town or site, "province": province,
        "employment_type": typ,
        "closing_date": closing,
        "reference_no": "RW-" + (one("reference number") or ref),
        "about_role": "\n".join([intro] + summary),
        "responsibilities": "\n".join(duties[:80]),
        "requirements": "\n".join(req[:80]),
        "official_apply_url": url, "source_url": url,
        "status": "live",
    })
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    import requests, sheet_writer
    s = requests.Session()
    s.headers["User-Agent"] = UA
    try:
        refs = list_jobs(s)
    except Exception as e:
        print(f"Rand Water: could not read the careers portal ({e})", file=sys.stderr)
        return
    print(f"Rand Water: {len(refs)} jobs on the portal", file=sys.stderr)
    rows, today = [], datetime.date.today().isoformat()
    for ref in refs:
        try:
            row = build_row(ref, get(s, f"{BASE}/Jobs/View/{ref}"), sheet_writer.COLUMNS)
            time.sleep(0.5)
        except Exception as e:
            print(f"  skipped {ref}: {e}", file=sys.stderr)
            continue
        if not row["job_title"] or (not row["responsibilities"] and not row["requirements"]):
            print(f"  skipped (could not read the advert): {ref}", file=sys.stderr)
            continue
        if row["closing_date"] and row["closing_date"] < today:
            continue
        rows.append(row)
    if a.dry_run:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        print(f"Rand Water: {len(rows)} jobs", file=sys.stderr)
        return
    try:
        new, upd = sheet_writer.upsert_jobs(rows, update_fields=("closing_date", "about_role", "responsibilities", "requirements"))
        gone = sheet_writer.retire_missing(EMPLOYER, {r["reference_no"] for r in rows}) if rows else 0
        print(f"Rand Water: found {len(rows)}, wrote {new} new, updated {upd}, closed {gone} no longer listed.", file=sys.stderr)
    except Exception as e:
        print(f"Rand Water: could not save ({e})", file=sys.stderr)


if __name__ == "__main__":
    main()
