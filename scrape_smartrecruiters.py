"""scrape_smartrecruiters.py  -  OnboardingSA

Company careers sites on SmartRecruiters, e.g. Standard Bank Group:
  list:   GET https://api.smartrecruiters.com/v1/companies/{company}/postings?country=za&limit=100&offset=N
  advert: GET https://api.smartrecruiters.com/v1/companies/{company}/postings/{id}
          -> jobAd.sections: jobDescription / qualifications / additionalInformation (company text is skipped)
Only South African posts. Fixed rules, no AI. Never fails the daily run.
Usage:  python scrape_smartrecruiters.py [--dry-run]
"""
import re, sys, json, time, html, argparse, datetime

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
API = "https://api.smartrecruiters.com/v1/companies/{company}/postings"

SITES = [
    {"employer": "Standard Bank", "company": "StandardBankGroup", "ref": "SB",
     "skip": r"standard bank group is a leading africa-focused|we.re passionate about creating growth in africa"},
    {"employer": "Valterra Platinum", "company": "ValterraPlatinum1", "ref": "VP", "all_countries": True,
     "skip": r"valterra platinum, formerly|valterra platinum is one of the world|what we offer|equal opportunit|zero tolerance to dignity"},
]
REGION = {"GP": "Gauteng", "WC": "Western Cape", "KZN": "KwaZulu-Natal", "NL": "KwaZulu-Natal", "EC": "Eastern Cape",
          "FS": "Free State", "NW": "North West", "NC": "Northern Cape", "LP": "Limpopo", "MP": "Mpumalanga",
          "GAUTENG": "Gauteng", "WESTERN CAPE": "Western Cape", "KWAZULU-NATAL": "KwaZulu-Natal", "KWAZULU NATAL": "KwaZulu-Natal",
          "EASTERN CAPE": "Eastern Cape", "FREE STATE": "Free State", "NORTH WEST": "North West", "NORTHERN CAPE": "Northern Cape",
          "LIMPOPO": "Limpopo", "MPUMALANGA": "Mpumalanga"}
HEAD = re.compile(r"^(job )?(key )?responsibilit\w*( include)?\b.*:?$|^(key )?duties\b.*:?$", re.I)


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
        cq = "" if cfg.get("all_countries") else "country=za&"
        d = get(s, API.format(company=cfg["company"]) + f"?{cq}limit=100&offset={offset}")
        items = d.get("content") or []
        out += items
        offset += 100
        if not items or offset >= (d.get("totalFound") or 0):
            break
    return out


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_date(s):
    """'19/11/2026', '2026-11-19', '18 November 2026', '18 Nov 2026' -> '2026-11-19'."""
    s = (s or "").strip()
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d\d)\b", s)
        if m:
            d, mo, y = map(int, m.groups())
        else:
            m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3})[a-z]*,?\s+(20\d\d)\b", s)
            if not m or m.group(2).lower() not in MONTHS:
                return ""
            d, mo, y = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3))
    try:
        return datetime.date(y, mo, d).isoformat()
    except ValueError:
        return ""


def custom(j, pattern):
    for f in j.get("customField") or []:
        if re.search(pattern, f.get("fieldLabel") or "", re.I):
            return (f.get("valueLabel") or "").strip()
    return ""


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
    clean = lambda xs: [y for y in (re.sub(r"\s+", " ", html.unescape(x)).strip() for x in xs) if y]
    about = [x for x in clean(about) if not HEAD.match(x)]
    resp, req = clean(resp), [re.sub(r"\s+Section:?$", ":", x) for x in clean(req)]
    about = [x for x in about if x not in resp]
    title = re.sub(r"\s+", " ", j.get("name") or "").strip()
    loc = j.get("location") or {}
    city = (loc.get("city") or "").strip()
    country = (loc.get("country") or "za").lower()
    COUNTRY = {"zw": "Zimbabwe", "bw": "Botswana", "na": "Namibia", "zm": "Zambia", "mz": "Mozambique", "gb": "United Kingdom",
               "sg": "Singapore", "cn": "China", "ls": "Lesotho", "sz": "Eswatini"}
    province = (REGION.get((loc.get("region") or "").upper(), "") or province_of(city)) if country == "za" else \
        COUNTRY.get(country, country.upper())
    place = ", ".join(x for x in (city, province) if x)
    te = ((j.get("typeOfEmployment") or {}).get("label") or "") + " " + custom(j, r"employment class|contract type")
    typ = ("Internship" if re.search(r"intern|graduate|learnership|bursar|apprentice|trainee", title, re.I) else
           "Contract" if re.search(r"contract|temporary|fixed", te + " " + title, re.I) else
           "Part-time" if "part" in te.lower() else "Full-time")
    art = "an" if re.match(r"[AEIOU]", title) else "a"
    intro = f"{cfg['employer']} is hiring {art} {title}" + (f", based in {place}" if place else "") + "."
    cat = guess_category(title, cfg["employer"])
    if cat in ("", "Government", "Other", "General"):
        cat = custom(j, r"^discipline$|job family") or ((j.get("function") or {}).get("label") or "") or cat
    alltext = " ".join(txt(k) for k in ("jobDescription", "qualifications", "additionalInformation"))
    closing = parse_date(custom(j, r"clos\w* date|deadline|expir")) or \
        parse_date((re.search(r"(?i)clos\w*\s*date\s*(?:<[^>]+>|\s|:|&nbsp;|&#xa0;)*([^<]{6,40})", alltext) or [None, ""])[1])
    url = j.get("postingUrl") or j.get("applyUrl") or ""
    row = {k: "" for k in columns}
    row.update({
        "job_title": title, "employer": cfg["employer"],
        "category": "" if cat == "Government" else cat,
        "location": city, "province": province,
        "employment_type": typ,
        "posted_date": (j.get("releasedDate") or "")[:10],
        "closing_date": closing,
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
    print(f"{cfg['employer']}: {len(items)} jobs on SmartRecruiters", file=sys.stderr)
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
            new, upd = sheet_writer.upsert_jobs(rows, update_fields=("about_role", "responsibilities", "requirements", "closing_date", "category", "employment_type"))
            gone = sheet_writer.retire_missing(cfg["employer"], {r["reference_no"] for r in rows}) if rows else 0
            print(f"{cfg['employer']}: found {len(rows)}, wrote {new} new, updated {upd}, closed {gone} no longer listed.", file=sys.stderr)
        except Exception as e:
            print(f"{cfg['employer']}: could not save ({e})", file=sys.stderr)


if __name__ == "__main__":
    main()
