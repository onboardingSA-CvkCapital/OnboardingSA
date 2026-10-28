"""scrape_oracle.py  -  OnboardingSA

Company careers sites on Oracle Recruiting Cloud (Candidate Experience), e.g. TFG:
  https://fa-expc-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs
  list:   GET /hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true
              &finder=findReqs;siteNumber=CX_1,limit=25,offset=N,sortBy=POSTING_DATES_DESC
  advert: GET /hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all&onlyData=true
              &finder=ById;Id="<id>",siteNumber=CX_1
Only South African posts are kept. Fixed rules, no AI. Never fails the daily run.
Usage:  python scrape_oracle.py [--dry-run]
"""
import re, sys, json, time, argparse, datetime, html as _h

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

SITES = [
    {"employer": "TFG", "host": "https://fa-expc-saasfaprod1.fa.ocs.oraclecloud.com", "site": "CX_1", "ref": "TFG",
     "skip": r"who we are is because of our people|tfg is an internationally diversified|are you with us"},
]

PROV = {"kwazulu natal": "KwaZulu-Natal", "kwazulu-natal": "KwaZulu-Natal", "gauteng": "Gauteng", "western cape": "Western Cape",
        "eastern cape": "Eastern Cape", "free state": "Free State", "limpopo": "Limpopo", "mpumalanga": "Mpumalanga",
        "north west": "North West", "northern cape": "Northern Cape"}


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
    out, offset, total = [], 0, None
    while offset < 3000:
        d = get(s, f"{cfg['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true"
                   f"&finder=findReqs;siteNumber={cfg['site']},limit=25,offset={offset},sortBy=POSTING_DATES_DESC")
        item = (d.get("items") or [{}])[0]
        reqs = item.get("requisitionList") or []
        if total is None:
            total = item.get("TotalJobsCount") or 0
        out += reqs
        offset += 25
        if not reqs or offset >= total:
            break
        time.sleep(0.5)
    return out


def sast(ts):
    """'2026-11-05T22:00:00+00:00' -> '2026-11-06' (midnight South African time)."""
    try:
        d = datetime.datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
        return (d + datetime.timedelta(hours=2)).date().isoformat()
    except Exception:
        return (ts or "")[:10]


def build_row(cfg, x, columns):
    from sa_places import province_of
    from scrape_dpsa import guess_category
    from advert_sections import sections
    desc = "\n".join(x.get(k) or "" for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr"))
    about, resp, req = sections(desc, re.compile(cfg["skip"], re.I))
    title = re.sub(r"\s+", " ", x.get("Title") or "").strip()
    parts = [p.strip() for p in re.split(r"\s+-\s+", title) if p.strip()]
    brand = parts[1] if len(parts) >= 3 else ""
    town = parts[-1] if len(parts) >= 3 else ""
    region = re.sub(r",?\s*South Africa\s*$", "", x.get("PrimaryLocation") or "").strip()
    province = PROV.get(region.lower(), "") or province_of(town) or province_of(region)
    loc = ", ".join(p for p in (town, province) if p) or region
    plain = _h.unescape(re.sub(r"<[^>]+>", " ", desc))
    sched = (x.get("JobSchedule") or "").lower()
    typ = ("Internship" if re.search(r"intern|graduate|learnership|bursar|apprentice|trainee", title, re.I) else
           "Contract" if re.search(r"fixed[- ]term|\bcontract\b|temporary|seasonal", title + " " + plain[:500], re.I) else
           "Part-time" if "part" in sched or re.search(r"flexi|part[- ]time", title, re.I) else "Full-time")
    who = f"{cfg['employer']} ({brand})" if brand else cfg["employer"]
    art = "an" if re.match(r"[AEIOU]", parts[0] if parts else title) else "a"
    intro = f"{who} is hiring {art} {parts[0] if parts else title}" + (f", based in {loc}" if loc else "") + "."
    cat = guess_category(title, cfg["employer"])
    url = f"{cfg['host']}/hcmUI/CandidateExperience/en/sites/{cfg['site']}/job/{x.get('Id')}"
    row = {k: "" for k in columns}
    row.update({
        "job_title": title, "employer": cfg["employer"],
        "category": "" if cat == "Government" else cat,
        "location": loc, "province": province,
        "employment_type": typ,
        "posted_date": (x.get("ExternalPostedStartDate") or "")[:10],
        "closing_date": sast(x.get("ExternalPostedEndDate")) if x.get("ExternalPostedEndDate") else "",
        "reference_no": f"{cfg['ref']}-{x.get('Id')}",
        "about_role": "\n".join([intro] + (about if not (resp or req) else about[:8])),
        "responsibilities": "\n".join(resp[:80]),
        "requirements": "\n".join(req[:80]),
        "official_apply_url": url, "source_url": url,
        "status": "live",
    })
    return row


def scrape_site(s, cfg, columns):
    reqs = list_jobs(s, cfg)
    print(f"{cfg['employer']}: {len(reqs)} jobs on the careers site", file=sys.stderr)
    rows, today = [], datetime.date.today().isoformat()
    for r in reqs:
        if (r.get("PrimaryLocationCountry") or "ZA") != "ZA":
            continue
        try:
            d = get(s, f"{cfg['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all&onlyData=true"
                       f"&finder=ById;Id=%22{r['Id']}%22,siteNumber={cfg['site']}")
            x = (d.get("items") or [{}])[0]
            row = build_row(cfg, x, columns)
            time.sleep(0.3)
        except Exception as e:
            print(f"  skipped {r.get('Title')}: {e}", file=sys.stderr)
            continue
        if not row["responsibilities"] and not row["requirements"] and len(row["about_role"].split()) < 70:
            print(f"  skipped (could not read duties/requirements): {row['job_title']}", file=sys.stderr)
            continue
        if row["closing_date"] and row["closing_date"] < today:
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
            new, upd = sheet_writer.upsert_jobs(rows, update_fields=("closing_date", "about_role", "responsibilities", "requirements"))
            gone = sheet_writer.retire_missing(cfg["employer"], {r["reference_no"] for r in rows}) if rows else 0
            print(f"{cfg['employer']}: found {len(rows)}, wrote {new} new, updated {upd}, closed {gone} no longer listed.", file=sys.stderr)
        except Exception as e:
            print(f"{cfg['employer']}: could not save ({e})", file=sys.stderr)


if __name__ == "__main__":
    main()
