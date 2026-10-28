"""scrape_transnet.py  -  OnboardingSA

Transnet Talent Portal (Cornerstone OnDemand):
  https://transnettalentportal.csod.com/ux/ats/careersite/1/home?c=transnettalentportal
  * the career site page carries a guest token (csod.context.token) and the API host (endpoints.cloud)
  * job list:   POST {cloud}rec-job-search/external/jobs           (Bearer token)
  * job advert: GET  /Services/API/ATS/CareerSite/1/JobRequisitions/{id}?cultureId=2   (Bearer token)
    -> the advert HTML: a snapshot table (division, employee group, location, grade, reference),
       the closing date, then sections: Position Purpose / Position Outputs /
       Qualifications and Experience / Competencies / Equity Statement.
Fixed rules, no AI. Never fails the daily run.
Usage:  python scrape_transnet.py [--dry-run]
"""
import re, sys, json, html, time, argparse, datetime

SITE = "https://transnettalentportal.csod.com"
HOME = SITE + "/ux/ats/careersite/1/home?c=transnettalentportal"
JOB_URL = SITE + "/ux/ats/careersite/1/home/requisition/{id}?c=transnettalentportal"
EMPLOYER = "Transnet"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
CULTURE = 2   # en-GB


def session_and_token():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = UA
    page = s.get(HOME, timeout=60).text
    m = re.search(r"csod\.context\s*=\s*(\{.*?\});", page, re.S)
    ctx = json.loads(m.group(1)) if m else {}
    token = ctx.get("token") or (re.search(r'"token":"([^"]+)"', page) or [None, None])[1]
    cloud = (ctx.get("endpoints") or {}).get("cloud") or "https://uk.api.csod.com/"
    if not token:
        token = token_from_browser()
    if not token:
        raise RuntimeError("no guest token on the career site page")
    s.headers.update({"Authorization": "Bearer " + token, "csod-accept-language": "en-GB",
                      "Accept": "application/json"})
    return s, cloud


def token_from_browser():
    """Fallback: open the page in Chromium and read the token the site uses."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(user_agent=UA)
            pg.goto(HOME, wait_until="domcontentloaded", timeout=90000)
            tok = pg.evaluate("() => (window.csod && csod.context && csod.context.token) || null")
            b.close()
            return tok
    except Exception as e:
        print(f"  browser fallback failed: {e}", file=sys.stderr)
        return None


def list_jobs(s, cloud):
    out, page = [], 1
    while True:
        body = {"careerSiteId": 1, "careerSitePageId": 1, "pageNumber": page, "pageSize": 100, "cultureId": CULTURE,
                "searchText": "", "cultureName": "en-GB", "states": [], "countryCodes": [], "cities": [], "placeID": "",
                "radius": None, "postingsWithinDays": None, "customFieldCheckboxKeys": [], "customFieldDropdowns": [],
                "customFieldRadios": []}
        r = s.post(cloud.rstrip("/") + "/rec-job-search/external/jobs", json=body, timeout=60)
        r.raise_for_status()
        d = r.json().get("data") or {}
        reqs = d.get("requisitions") or []
        out += reqs
        if not reqs or len(out) >= (d.get("totalCount") or 0) or page > 20:
            return out
        page += 1


def advert(s, rid):
    for n in range(3):
        try:
            r = s.get(f"{SITE}/Services/API/ATS/CareerSite/1/JobRequisitions/{rid}?useMobileAd=false&cultureId={CULTURE}", timeout=60)
            r.raise_for_status()
            return r.json()["data"][0]["items"][0]["fields"]
        except Exception:
            if n == 2:
                raise
            time.sleep(3 * (n + 1))


def clean(t):
    t = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", t or "", flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("\xa0", " ")
    return "\n".join(re.sub(r"[ \t]+", " ", x).strip() for x in t.split("\n"))


def bullets(t):
    """Section text -> list of items. Splits on the '•' markers; keeps short sub-headings like 'Skills Required:'."""
    items = []
    for line in clean(t).split("\n"):
        for part in re.split(r"\s*•\s*", line):
            part = part.strip(" ,;")
            if len(part) < 2:
                continue
            if not line.strip().startswith("•") and len(part) < 40 and not part.endswith((".", ",")) and part == line.strip():
                part = part.rstrip(":") + ":"      # e.g. 'Standard Job Requirements'
            items.append(part[0].upper() + part[1:])
    while items and items[-1].endswith(":"):
        items.pop()
    return items


def parse_ad(ad_html):
    body = ad_html[ad_html.lower().find("<body"):] if "<body" in ad_html.lower() else ad_html
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)                     # recruiter e-mail lives in comments
    snap = {html.unescape(re.sub(r"<[^>]+>", "", k)).strip().rstrip(":").lower(): clean(v).strip()
            for k, v in re.findall(r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>", body, re.S)}
    closing = ""
    m = re.search(r"closing date is (?:on )?(?:<[^>]+>)*\s*(\d{1,2})/(\d{1,2})/(\d{4})", body, re.I)
    if m:
        closing = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    sections = {}
    for head, sec in re.findall(r'<div class="sectionheader">(.*?)</div>\s*<div class="sectionbody">(.*?)</div>', body, re.S):
        sections[clean(head).strip().lower()] = sec
    pick = lambda *names: next((sections[k] for k in sections for n in names if k.startswith(n)), "")
    purpose = " ".join(clean(pick("position purpose", "purpose")).split())
    resp = bullets(pick("position outputs", "outputs", "key responsibilities", "responsibilities", "duties"))
    req = bullets(pick("qualifications and experience", "qualification", "requirements", "minimum requirements"))
    comp = bullets(pick("competencies", "skills"))
    if comp:
        req += ["Competencies:"] + comp
    pwd = bool(re.search(r"Persons with Disability", body, re.I))
    return snap, closing, purpose, resp, req, pwd


def dmy(s):
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s or "")
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else ""


def emp_type(group, title):
    g = (group or "").lower()
    if re.search(r"learnership|intern|graduate|bursar|apprentice|trainee", title, re.I) or re.search(r"learner|intern|trainee", g):
        return "Internship"
    if "fixed" in g or "contract" in g or "temporary" in g:
        return "Contract"
    if "permanent" in g:
        return "Permanent"
    return "Full-time"


def build_row(r, ad, columns):
    from sa_places import province_of
    from scrape_dpsa import guess_category
    snap, closing, purpose, resp, req, pwd = parse_ad(ad.get("ad", ""))
    title = re.sub(r"\s+", " ", r.get("displayJobTitle") or ad.get("title") or "").strip()
    city = (snap.get("location") or ad.get("location") or (r.get("locations") or [{}])[0].get("city") or "").strip()
    division = snap.get("operating division", "")
    art = "an" if re.match(r"[AEIOU]", title) else "a"
    intro = f"Transnet{' (' + division + ')' if division else ''} is hiring {art} {title}" + (f", based in {city}" if city else "") + "."
    if snap.get("reporting to"):
        intro += f" The role reports to the {snap['reporting to'].rstrip('.')}."
    if snap.get("grade"):
        intro += f" Grade: {snap['grade']}."
    if pwd:
        intro += " Preference will be given to persons with disabilities."
    cat = guess_category(title, EMPLOYER)
    ref = (snap.get("reference") or ad.get("reqId") or f"req{r['requisitionId']}").strip()
    row = {k: "" for k in columns}
    row.update({
        "job_title": title, "employer": EMPLOYER,
        "category": "" if cat == "Government" else cat,
        "location": city, "province": province_of(city),
        "employment_type": emp_type(snap.get("employee group"), title),
        "posted_date": dmy(r.get("postingEffectiveDate")),
        "closing_date": closing or dmy(r.get("postingExpirationDate")),
        "reference_no": "TRANSNET-" + ref,
        "about_role": "\n".join(x for x in (intro, purpose) if x),
        "responsibilities": "\n".join(resp[:30]),
        "requirements": "\n".join(req[:40]),
        "official_apply_url": JOB_URL.format(id=r["requisitionId"]),
        "source_url": JOB_URL.format(id=r["requisitionId"]),
        "status": "live",
    })
    return row


def scrape(columns):
    s, cloud = session_and_token()
    reqs = list_jobs(s, cloud)
    print(f"Transnet: {len(reqs)} jobs on the talent portal", file=sys.stderr)
    rows, today = [], datetime.date.today().isoformat()
    for r in reqs:
        try:
            if any((l.get("country") or "ZA") != "ZA" for l in (r.get("locations") or [])):
                continue
            row = build_row(r, advert(s, r["requisitionId"]), columns)
            time.sleep(0.5)
        except Exception as e:
            print(f"  skipped {r.get('displayJobTitle')}: {e}", file=sys.stderr)
            continue
        if not row["responsibilities"] or not row["requirements"]:
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
    import sheet_writer
    try:
        rows = scrape(sheet_writer.COLUMNS)
    except Exception as e:
        print(f"Transnet: could not read the talent portal ({e})", file=sys.stderr)
        return
    if a.dry_run:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        print(f"{len(rows)} jobs", file=sys.stderr)
        return
    new, upd = sheet_writer.upsert_jobs(rows, update_fields=("closing_date", "about_role", "responsibilities", "requirements"))
    print(f"Transnet: found {len(rows)}, wrote {new} new, updated {upd}.", file=sys.stderr)


if __name__ == "__main__":
    main()
