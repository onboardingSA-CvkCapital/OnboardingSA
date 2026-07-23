import re, sys, time, html, json
import requests
import sheet_writer

BASE = "https://www.careers24.com"
LIST_URL = BASE + "/jobs/rmt-incl/"
RECENT_DAYS = 7
MAX_PAGES = 200
RELAY = ""

COLUMNS = sheet_writer.COLUMNS
HEADERS = {
    "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language":"en-US,en;q=0.9",
}

PROVINCE_MAP = {
    "eastern cape":"Eastern Cape","free state":"Free State","gauteng":"Gauteng",
    "kwazulu-natal":"KwaZulu-Natal","kwazulu natal":"KwaZulu-Natal","limpopo":"Limpopo",
    "mpumalanga":"Mpumalanga","north west":"North West","northern cape":"Northern Cape",
    "western cape":"Western Cape",
}

EMPTYPE = {
    "FULL_TIME":"Permanent","PART_TIME":"Part-Time","CONTRACTOR":"Contract",
    "TEMPORARY":"Temporary","INTERN":"Internship","OTHER":"",
}

def fetch(session, url):
    target = (RELAY + "/?url=" + requests.utils.quote(url, safe="")) if RELAY else url
    for _ in range(3):
        try:
            r = session.get(target, headers=HEADERS, timeout=45)
            if r.status_code == 200:
                return r.text
            if r.status_code in (404,410):
                return ""
        except Exception:
            time.sleep(2)
    return None

def province_of(region, locality):
    for v in (region, locality):
        k = (v or "").strip().lower()
        if k in PROVINCE_MAP:
            return PROVINCE_MAP[k]
    return (region or "").strip()

def strip_html(h):
    h = re.sub(r'(?is)<li[^>]*>', '\n\u2022 ', h)
    h = re.sub(r'(?is)</li>', '', h)
    h = re.sub(r'(?is)<br\s*/?>', '\n', h)
    h = re.sub(r'(?is)</p>', '\n', h)
    h = re.sub(r'(?is)<h[1-6][^>]*>', '\n', h)
    h = re.sub(r'(?is)</h[1-6]>', '\n', h)
    h = re.sub(r'(?is)<strong[^>]*>', '', h)
    h = re.sub(r'(?is)</strong>', '', h)
    h = re.sub(r'(?is)<[^>]+>', '', h)
    return html.unescape(h)

def clean(t, limit=8000):
    if not t: return ""
    out = "\n".join(x for x in (re.sub(r'[ \t]+',' ',l).strip() for l in t.split('\n')) if x)
    return out[:limit].rstrip()

def list_job_urls(page_html):
    urls = []
    for m in re.finditer(r'href="(/jobs/adverts/(\d+)-[^"?]+/)(?:\?[^"]*)?"\s+data-control="vacancy-title"', page_html):
        urls.append((m.group(2), BASE + m.group(1)))
    if not urls:
        for m in re.finditer(r'href="(/jobs/adverts/(\d+)-[^"?]+/)', page_html):
            urls.append((m.group(2), BASE + m.group(1)))
    seen = set(); out = []
    for jid, u in urls:
        if jid not in seen:
            seen.add(jid); out.append((jid, u))
    return out

def parse_detail(detail_html):
    m = re.search(r'(?is)<script type="application/ld\+json">\s*(\{.*?"JobPosting".*?\})\s*</script>', detail_html)
    data = {}
    if m:
        try:
            data = json.loads(m.group(1))
        except Exception:
            data = {}
    title = html.unescape(data.get("title","") or "")
    posted = data.get("datePosted","") or ""
    closing = data.get("validThrough","") or ""
    industry = html.unescape(data.get("industry","") or "")
    emptype = EMPTYPE.get(data.get("employmentType",""), "")
    org = ((data.get("hiringOrganization") or {}).get("name","") or "").strip()
    org = html.unescape(org)
    loc = (data.get("jobLocation") or {}).get("address") or {}
    locality = html.unescape(loc.get("addressLocality","") or "")
    region = html.unescape(loc.get("addressRegion","") or "")
    country = (loc.get("addressCountry","") or "").strip().lower()
    salary = ""
    bs = data.get("baseSalary") or {}
    val = (bs.get("value") or {})
    if val.get("value"):
        cur = bs.get("currency","ZAR")
        unit = (val.get("unitText","") or "").title()
        salary = f"{cur} {val.get('value')}" + (f" / {unit}" if unit else "")
    dm = re.search(r'(?is)<div class="v-descrip">(.*?)</div>\s*(?:<div class="v-descrip">(.*?)</div>)?\s*</div>\s*</div>', detail_html)
    desc_html = ""
    for block in re.findall(r'(?is)<div class="v-descrip">(.*?)</div>', detail_html):
        desc_html += "\n" + block
    about = clean(strip_html(desc_html)) if desc_html else html.unescape(data.get("description","") or "")
    ref = ""
    rm = re.search(r'(?is)Reference:\s*([A-Za-z0-9/_\-]+)', detail_html)
    if rm: ref = rm.group(1).strip()
    return {
        "title":title,"posted":posted,"closing":closing,"industry":industry,
        "emptype":emptype,"org":org,"locality":locality,"region":region,
        "country":country,"salary":salary,"about":about,"ref":ref,
    }

def scrape():
    total=0; skipped_foreign=0
    with requests.Session() as s:
        for pg in range(1, MAX_PAGES+1):
            list_url = f"{LIST_URL}?page={pg}&posted={RECENT_DAYS}"
            page_html = fetch(s, list_url)
            if page_html is None:
                print(f"page {pg}: fetch failed - stopping.", file=sys.stderr); break
            jobs = list_job_urls(page_html)
            if not jobs:
                print(f"page {pg}: no jobs - stopping.", file=sys.stderr); break
            print(f"Page {pg}: {len(jobs)} jobs", file=sys.stderr)
            rows=[]
            for jid, url in jobs:
                dhtml = fetch(s, url)
                if not dhtml:
                    continue
                d = parse_detail(dhtml)
                if not d["title"]:
                    continue
                if d["country"] and "south africa" not in d["country"]:
                    skipped_foreign += 1
                    continue
                row = {k:"" for k in COLUMNS}
                row.update({
                    "job_title": d["title"],
                    "employer": d["org"],
                    "category": d["industry"],
                    "province": province_of(d["region"], d["locality"]),
                    "location": d["locality"] or d["region"],
                    "employment_type": d["emptype"],
                    "salary": d["salary"],
                    "posted_date": d["posted"],
                    "closing_date": d["closing"],
                    "reference_no": d["ref"] or ("c24_"+jid),
                    "about_role": d["about"],
                    "official_apply_url": url,
                    "source_url": url,
                    "status": "live",
                })
                rows.append(row)
                print(f"  [{jid}] {d['title'][:45]}", file=sys.stderr)
                time.sleep(0.3)
            if rows:
                wrote = sheet_writer.append_jobs(rows); total += wrote
                print(f"  wrote {wrote} new (total {total})", file=sys.stderr)
            time.sleep(0.4)
    print(f"\nSkipped {skipped_foreign} non-SA.", file=sys.stderr)
    return total

def main():
    print("Careers24 (last {} days)...".format(RECENT_DAYS), file=sys.stderr)
    total = scrape()
    print(f"Done: wrote {total} new Careers24 jobs.", file=sys.stderr)

if __name__ == "__main__":
    main()
