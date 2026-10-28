"""scrape_aeci.py  -  OnboardingSA

AECI careers (SAP SuccessFactors career site): https://jobs.aeciworld.com/search/
  * search pages: <tr class="data-row"> rows with <a class="jobTitle-link" href="/job/.../<id>/">, paged with startrow=
  * job pages: schema.org microdata (title, datePosted, validThrough, addressLocality/Region/Country)
    and the advert in <span class="jobdescription"> with bold headings:
    Purpose of the Job / Roles and Responsibilities / Qualifications and Experience / Key Competencies
Fixed rules, no AI. Never fails the daily run.
Usage:  python scrape_aeci.py [--dry-run]
"""
import re, sys, json, html, time, argparse, datetime

BASE = "https://jobs.aeciworld.com"
SEARCH = BASE + "/search/?q=&sortColumn=referencedate&sortDirection=desc&startrow={start}"
EMPLOYER = "AECI"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

REGION = {"GP": "Gauteng", "MP": "Mpumalanga", "KZN": "KwaZulu-Natal", "NL": "KwaZulu-Natal", "WC": "Western Cape",
          "EC": "Eastern Cape", "FS": "Free State", "NW": "North West", "NC": "Northern Cape", "LP": "Limpopo",
          "NP": "Limpopo"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

H_ABOUT = re.compile(r"^(purpose of the (job|role|position)|job purpose|role purpose|purpose|about the role|overview)\b", re.I)
H_RESP = re.compile(r"^(roles? and responsibilities|key responsibilities|responsibilities|duties|key performance areas|outputs)\b", re.I)
H_REQ = re.compile(r"^(qualifications?( and experience)?|minimum requirements|requirements|experience|education|"
                   r"key competencies|competencies|skills|knowledge|behavioural competencies|technical competencies)\b", re.I)
H_STOP = re.compile(r"^(aeci respects|aeci is an equal|equal opportunit|disclaimer|please note|closing date|"
                    r"if you do not hear|only shortlisted)", re.I)


def get(s, url, tries=3):
    last = None
    for n in range(tries):
        try:
            r = s.get(url, timeout=60)
            if r.status_code == 200:
                return r.text
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(3 * (n + 1))
    raise RuntimeError(f"{url}: {last}")


def text(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


def list_jobs(s):
    seen, out, start = set(), [], 0
    while start < 1000:
        page = get(s, SEARCH.format(start=start))
        rows = re.findall(r'<tr class="data-row">(.*?)</tr>', page, re.S)
        if not rows:
            break
        for r in rows:
            m = re.search(r'<a href="(/job/[^"]+/(\d+)/)" class="jobTitle-link">(.*?)</a>', r, re.S)
            if m and m.group(2) not in seen:
                seen.add(m.group(2))
                loc = re.search(r'<span class="jobLocation">\s*(.*?)\s*</span>', r, re.S)
                out.append({"path": m.group(1), "id": m.group(2), "title": text(m.group(3)),
                            "loc": text(loc.group(1)) if loc else ""})
        total = re.search(r"of\s*<b>\s*(\d+)\s*</b>", page)
        start += len(rows)
        if total and start >= int(total.group(1)):
            break
        time.sleep(1)
    return out


def meta(page, prop):
    m = re.search(r'<meta itemprop="%s" content="([^"]*)"' % prop, page)
    return html.unescape(m.group(1)).strip() if m else ""


def sast_date(s):
    """'Tue Nov 10 22:00:00 UTC 2026' -> '2026-11-11' (the site stores midnight South African time as 22:00 UTC)."""
    m = re.search(r"([A-Za-z]{3})\s+(\d{1,2})\s+(\d{1,2}):(\d{2}):\d{2}\s+UTC\s+(\d{4})", s or "")
    if not m or m.group(1).lower() not in MONTHS:
        return ""
    d = datetime.datetime(int(m.group(5)), MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3)), int(m.group(4)))
    return (d + datetime.timedelta(hours=2)).date().isoformat()


def sections(desc):
    about, resp, req, sec = [], [], [], None
    for m in re.finditer(r"<(p|li|h[1-6]|div)\b[^>]*>(.*?)</\1>", desc, re.S | re.I):
        tag, inner = m.group(1).lower(), m.group(2)
        t = text(inner)
        if not t or "<img" in inner and not t:
            continue
        head = t.rstrip(":").strip()
        is_head = tag.startswith("h") or (tag != "li" and re.fullmatch(r"\s*(<(strong|b)>.*?</\2>\s*)+:?\s*", inner, re.S | re.I)
                                          and len(head) < 70)
        if H_STOP.match(head):
            sec = "stop"
            continue
        if is_head:
            if H_ABOUT.match(head):
                sec = "about"
            elif H_RESP.match(head):
                sec = "resp"
            elif H_REQ.match(head):
                if sec == "req" or not re.match(r"^(qualifications?( and experience)?|minimum requirements|requirements)$", head, re.I):
                    req.append(head + ":")
                sec = "req"
            elif sec in ("resp", "req"):
                (resp if sec == "resp" else req).append(head + ":")
            continue
        if sec == "about":
            about.append(t)
        elif sec == "resp":
            resp.append(t)
        elif sec == "req":
            req.append(t)
    for lst in (resp, req):
        while lst and lst[-1].endswith(":"):
            lst.pop()
    return about, resp, req


def build_row(item, page, columns):
    from sa_places import province_of
    from scrape_dpsa import guess_category
    t = re.search(r'<span[^>]*itemprop="title"[^>]*>(.*?)</span>', page, re.S)
    title = re.sub(r"\s+", " ", text(t.group(1)) if t else item["title"]).strip()
    d = re.search(r'<span class="jobdescription">(.*?)</span>\s*</span>', page, re.S)
    about, resp, req = sections(d.group(1) if d else "")
    city = meta(page, "addressLocality") or item["loc"].split(",")[0].strip()
    province = REGION.get(meta(page, "addressRegion").upper(), "") or province_of(city)
    ref = re.search(r'data-careersite-propertyid="adcode"[^>]*>\s*([^<\s]+)', page)
    art = "an" if re.match(r"[AEIOU]", title) else "a"
    intro = f"AECI is hiring {art} {title}" + (f", based in {city}" if city else "") + "."
    cat = guess_category(title, EMPLOYER)
    typ = "Internship" if re.search(r"intern|graduate|learnership|bursar|apprentice|trainee", title, re.I) else \
          "Contract" if re.search(r"\b(contract|fixed[- ]term|temporary)\b", title + " " + " ".join(about), re.I) else "Full-time"
    url = BASE + item["path"]
    row = {k: "" for k in columns}
    row.update({
        "job_title": title, "employer": EMPLOYER,
        "category": "" if cat == "Government" else cat,
        "location": city, "province": province,
        "employment_type": typ,
        "posted_date": sast_date(meta(page, "datePosted")),
        "closing_date": sast_date(meta(page, "validThrough")),
        "reference_no": "AECI-" + (ref.group(1) if ref else item["id"]),
        "about_role": "\n".join([intro] + about),
        "responsibilities": "\n".join(resp[:30]),
        "requirements": "\n".join(req[:40]),
        "official_apply_url": url, "source_url": url,
        "status": "live",
    })
    return row


def scrape(columns):
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = UA
    items = list_jobs(s)
    print(f"AECI: {len(items)} jobs on the careers site", file=sys.stderr)
    rows, today = [], datetime.date.today().isoformat()
    for it in items:
        if it["loc"] and not re.search(r",\s*ZA\b", it["loc"]):
            print(f"  skip (outside SA): {it['title']} - {it['loc']}", file=sys.stderr)
            continue
        try:
            row = build_row(it, get(s, BASE + it["path"]), columns)
            time.sleep(1)
        except Exception as e:
            print(f"  skipped {it['title']}: {e}", file=sys.stderr)
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
        print(f"AECI: could not read the careers site ({e})", file=sys.stderr)
        return
    if a.dry_run:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        print(f"{len(rows)} jobs", file=sys.stderr)
        return
    new, upd = sheet_writer.upsert_jobs(rows, update_fields=("closing_date", "about_role", "responsibilities", "requirements"))
    print(f"AECI: found {len(rows)}, wrote {new} new, updated {upd}.", file=sys.stderr)


if __name__ == "__main__":
    main()
