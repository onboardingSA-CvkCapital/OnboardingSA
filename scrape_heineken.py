"""scrape_heineken.py  -  OnboardingSA

HEINEKEN careers, South Africa filter:
  https://careers.theheinekencompany.com/Job-Listing?field_location_country_code_1[]=ZA
  * listing pages: links /job/<company>/south-africa/<slug>, more pages via &page=0,0,N ("Show more")
  * job pages: JSON-LD JobPosting (datePosted, validThrough, employmentType), "Location:" line,
    and the advert in <div class="job-fields">
Fixed rules, no AI. Never fails the daily run.
Usage:  python scrape_heineken.py [--dry-run]
"""
import re, sys, json, html, time, argparse, datetime

BASE = "https://careers.theheinekencompany.com"
LIST = BASE + "/Job-Listing?field_location_country_code_1%5B0%5D=ZA&page=0%2C0%2C{n}"
EMPLOYER = "Heineken"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
SKIP = re.compile(r"recruitment process does not include unsolicited|will only contact you if you have applied|"
                  r"explore our world, explore your future", re.I)


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


def iso(s):
    """'Oct 21 2026' / '21 October 2026' -> '2026-10-21'."""
    m = re.search(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", s or "")
    if m and m.group(1).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?,?\s+(\d{4})", s or "")
    if m and m.group(2).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return ""


def list_jobs(s):
    links, n = [], 0
    while n < 40:
        page = get(s, LIST.format(n=n))
        found = [l for l in dict.fromkeys(re.findall(r'href="(/job/[a-z0-9-]+/south-africa/[a-z0-9-]+)"', page)) if l not in links]
        if not found:
            break
        links += found
        if "Show more" not in page:
            break
        n += 1
        time.sleep(1)
    return links


def build_row(path, page, columns):
    from sa_places import province_of
    from scrape_dpsa import guess_category
    from advert_sections import sections
    ld = {}
    for m in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            d = json.loads(m)
        except Exception:
            continue
        for x in (d.get("@graph") or [d]) if isinstance(d, dict) else []:
            if isinstance(x, dict) and x.get("@type") == "JobPosting":
                ld = x
    t = re.search(r'<h1 class="job-title[^"]*">(.*?)</h1>', page, re.S)
    title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", t.group(1) if t else ld.get("title", "")))).strip()
    loc = re.search(r"<strong>Location:</strong>\s*([^<]+)", page)
    place = re.sub(r",?\s*South Africa\s*$", "", html.unescape(loc.group(1)).strip()) if loc else ""
    m = re.search(r'<div class="job-fields">(.*?)</div>\s*</div>', page, re.S)
    desc = m.group(1) if m else ""
    about, resp, req = sections(desc, SKIP)
    plain = html.unescape(re.sub(r"<[^>]+>", " ", desc))
    cm = re.search(r"closing date\s*:?\s*([^\n<]{6,40})", plain, re.I)
    closing = iso(ld.get("validThrough", "")) or (iso(cm.group(1)) if cm else "")
    et = (ld.get("employmentType") or "")
    typ = ("Internship" if re.search(r"graduate|intern|learnership|bursar|apprentice|trainee", title, re.I) else
           "Contract" if re.search(r"contract|temp|fixed", et + " " + title, re.I) else
           "Permanent" if "permanent" in et.lower() else "Full-time")
    art = "an" if re.match(r"[AEIOU]", title) else "a"
    intro = f"Heineken Beverages is hiring {art} {title}" + (f", based in {place}" if place else "") + "."
    cat = guess_category(title, EMPLOYER)
    url = BASE + path
    row = {k: "" for k in columns}
    row.update({
        "job_title": title, "employer": EMPLOYER,
        "category": "" if cat == "Government" else cat,
        "location": place, "province": province_of(place),
        "employment_type": typ,
        "posted_date": iso(ld.get("datePosted", "")),
        "closing_date": closing,
        "reference_no": "HEINEKEN-" + path.rsplit("/", 1)[-1],
        "about_role": "\n".join([intro] + (about if not (resp or req) else about[:8])),
        "responsibilities": "\n".join(resp[:80]),
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
        links = list_jobs(s)
    except Exception as e:
        print(f"Heineken: could not read the careers site ({e})", file=sys.stderr)
        return
    print(f"Heineken: {len(links)} South African jobs", file=sys.stderr)
    rows, today = [], datetime.date.today().isoformat()
    for path in links:
        try:
            row = build_row(path, get(s, BASE + path), sheet_writer.COLUMNS)
            time.sleep(1)
        except Exception as e:
            print(f"  skipped {path}: {e}", file=sys.stderr)
            continue
        if not row["responsibilities"] and not row["requirements"] and len(row["about_role"].split()) < 70:
            print(f"  skipped (could not read duties/requirements): {row['job_title']}", file=sys.stderr)
            continue
        if row["closing_date"] and row["closing_date"] < today:
            continue
        rows.append(row)
    if a.dry_run:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        print(f"{len(rows)} jobs", file=sys.stderr)
        return
    try:
        new, upd = sheet_writer.upsert_jobs(rows, update_fields=("closing_date", "about_role", "responsibilities", "requirements"))
        gone = sheet_writer.retire_missing(EMPLOYER, {r["reference_no"] for r in rows}) if rows else 0
        print(f"Heineken: found {len(rows)}, wrote {new} new, updated {upd}, closed {gone} no longer listed.", file=sys.stderr)
    except Exception as e:
        print(f"Heineken: could not save ({e})", file=sys.stderr)


if __name__ == "__main__":
    main()
