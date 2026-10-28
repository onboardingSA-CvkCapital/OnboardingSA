"""scrape_omnia.py  -  OnboardingSA

Omnia Holdings careers page (Manatal): https://omnia-holdings.careers-page.com/
  * the job list is plain HTML (one <a class="job-title-link" data-job-id=...> per job)
  * every job page carries a schema.org JobPosting (title, datePosted, description HTML, location)
  * the real closing date is in the advert text ("Submission Closing Date: 02 November 2026")

Only South African posts are kept. Fixed rules, no AI.
Usage:  python scrape_omnia.py            (writes to the sheet)
        python scrape_omnia.py --dry-run  (prints what it found)
        python scrape_omnia.py --from-dir DIR   (parse saved list.html / detail pages, for testing)
"""
import re, sys, json, html, argparse, datetime, os, time

BASE = "https://omnia-holdings.careers-page.com"
EMPLOYER = "Omnia"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}

# company text that is the same on every advert: not part of the job
BOILER = re.compile(r"^(join\b|as part of omnia|at omnia,|innovating to enhance|bme, a division|bme is |omnia's manufacturing|"
                    r"omnia nutriology|omnia is |we are |thank you|diversity|open application|"
                    r"omnia holdings is an equal|only shortlisted)", re.I)
HEAD_ABOUT = re.compile(r"^(role impact|role purpose|purpose of the role|job purpose|the role|about the role)\b", re.I)
HEAD_RESP = re.compile(r"^(key responsibilities|responsibilities|key performance areas|duties|main duties)\b", re.I)
HEAD_REQ = re.compile(r"^(minimum requirements|requirements|qualifications?( and experience)?|experience|"
                      r"key competencies|competencies|skills|knowledge|education)\b", re.I)
HEAD_STOP = re.compile(r"^(diversity|thank you|open application|equal opportunity|disclaimer|important)\b", re.I)
FIELD = re.compile(r"^(location|business unit|reports to|contract type|submission closing date|closing date|job title)\s*:?\s*(.*)$", re.I)


def get(url, tries=3):
    import requests
    last = None
    for n in range(tries):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=40)
            if r.status_code == 200:
                return r.text
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(3 * (n + 1))
    raise RuntimeError(f"{url}: {last}")


def text(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ").replace("\ufeff", "").replace("\u200b", "")
    return re.sub(r"[ \t]+", " ", s).strip()


def to_iso(s):
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s or "")
    if m and m.group(2).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", s or "")
    if m and m.group(1).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return ""


def parse_list(page):
    """[{id, title, city, country, unit}] from the careers list page."""
    out, seen = [], set()
    for m in re.finditer(r'<a href="/jobs/([0-9a-f-]{36})"\s+class="job-title-link[^"]*"(.*?)>', page, re.S):
        jid, attrs = m.group(1), m.group(2)
        if jid in seen:
            continue
        seen.add(jid)
        a = dict(re.findall(r'data-([a-z-]+)="([^"]*)"', attrs))
        tail = page[m.end():m.end() + 5000]
        spans = [text(x) for x in re.findall(r"<span>(.*?)</span>", tail, re.S)[:2]]
        out.append({"id": jid, "title": html.unescape(a.get("job-title", "")), "city": html.unescape(a.get("job-city", "")),
                    "country": html.unescape(a.get("job-country", "")), "unit": spans[1] if len(spans) > 1 else ""})
    return out


def blocks(desc_html):
    """The advert HTML as a list of ('p'|'li', text, is_heading)."""
    out = []
    for m in re.finditer(r"<(p|li|h[1-6])\b[^>]*>(.*?)</\1>", desc_html or "", re.S | re.I):
        tag, inner = m.group(1).lower(), m.group(2)
        t = text(inner)
        if not t:
            continue
        bold_only = bool(re.fullmatch(r"\s*<(strong|b)>.*?</\1>\s*:?\s*", inner, re.S | re.I))
        is_head = tag.startswith("h") or (tag == "p" and bold_only and len(t) < 70)
        out.append(("li" if tag == "li" else "p", t, is_head))
    return out


def parse_detail(page):
    ld = None
    for m in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            d = json.loads(m)
        except Exception:
            continue
        if isinstance(d, dict) and d.get("@type") == "JobPosting":
            ld = d
            break
    if not ld:
        raise ValueError("no JobPosting data on the page")
    fields, about, resp, req = {}, [], [], []
    section = None
    for kind, t, is_head in blocks(ld.get("description", "")):
        f = FIELD.match(t)
        if f and kind == "p" and len(t) < 160:
            fields[f.group(1).lower()] = f.group(2).strip()
            continue
        h = t.rstrip(":").strip()
        if is_head or (kind == "p" and len(h) < 40 and h.isupper()):
            if HEAD_STOP.match(h):
                section = "stop"
            elif HEAD_ABOUT.match(h):
                section = "about"
            elif HEAD_RESP.match(h):
                section = "resp"
            elif HEAD_REQ.match(h):
                section = "req"
                if not re.match(r"^(minimum requirements|requirements)$", h, re.I):
                    req.append(h.title() + ":")          # keep sub-headings like 'Qualifications:'
            elif section in ("resp", "req") and kind == "p":
                (resp if section == "resp" else req).append(h + ":")
            continue
        if section == "stop" or BOILER.match(t):
            continue
        if section == "about":
            about.append(t)
        elif section == "resp":
            resp.append(t)
        elif section == "req":
            req.append(t)
    # drop a trailing sub-heading with nothing under it
    while req and req[-1].endswith(":"):
        req.pop()
    loc = (ld.get("jobLocation") or {}).get("address") or {}
    return ld, fields, about, resp, req, loc


def job_type(fields, ld, title):
    ct = (fields.get("contract type") or "").lower()
    if re.search(r"graduate|intern|learnership|bursar", title, re.I):
        return "Internship"
    if "fixed" in ct or "contract" in ct or "temporary" in ct:
        return "Contract"
    if "permanent" in ct:
        return "Permanent"
    return {"FULL_TIME": "Full-time", "PART_TIME": "Part-time", "CONTRACTOR": "Contract",
            "TEMPORARY": "Contract", "INTERN": "Internship"}.get(ld.get("employmentType", ""), "Full-time")


def build_row(item, page, columns):
    from sa_places import province_of
    from scrape_dpsa import guess_category
    ld, fields, about, resp, req, loc = parse_detail(page)
    title = re.sub(r"\s+", " ", ld.get("title") or item["title"]).strip()
    place = fields.get("location") or ", ".join(x for x in (loc.get("addressLocality"), item.get("city")) if x)
    place = re.sub(r",?\s*South Africa\.?$", "", place.replace("\ufeff", ""), flags=re.I).strip(" ,")
    place = re.sub(r"(?<!,)\s+(Mpumalanga|Gauteng|Limpopo|Free State|North West|Northern Cape|Western Cape|Eastern Cape|KwaZulu-Natal)$",
                   r", \1", place)
    province = province_of(place) or province_of(item.get("city", ""))
    closing = to_iso(fields.get("submission closing date") or fields.get("closing date") or "") or (ld.get("validThrough") or "")[:10]
    unit = fields.get("business unit") or item.get("unit") or ""
    unit = unit.replace(" | ", ", ")
    art = "an" if re.match(r"[AEIOU]", title) else "a"
    intro = f"Omnia is hiring {art} {title}" + (f" in {unit}" if unit else "") + (f", based in {place}" if place else "") + "."
    if fields.get("reports to"):
        intro += f" The role reports to the {fields['reports to'].rstrip('.')}."
    cat = guess_category(title, EMPLOYER)
    row = {k: "" for k in columns}
    row.update({
        "job_title": title, "employer": EMPLOYER,
        "category": "" if cat == "Government" else cat,
        "province": province, "location": place,
        "employment_type": job_type(fields, ld, title),
        "posted_date": (ld.get("datePosted") or "")[:10],
        "closing_date": closing,
        "reference_no": "OMNIA-" + item["id"][:8].upper(),
        "about_role": "\n".join([intro] + about),
        "responsibilities": "\n".join(resp[:80]),
        "requirements": "\n".join(req[:80]),
        "official_apply_url": f"{BASE}/jobs/{item['id']}",
        "source_url": f"{BASE}/jobs/{item['id']}",
        "status": "live",
    })
    return row


def scrape(from_dir=None):
    columns = __import__("sheet_writer").COLUMNS if not from_dir else [
        "id", "job_title", "employer", "category", "province", "location", "employment_type", "salary", "posted_date",
        "closing_date", "reference_no", "about_role", "responsibilities", "requirements", "official_apply_url",
        "source_url", "featured", "status"]
    listing = open(os.path.join(from_dir, "list.html"), encoding="utf-8").read() if from_dir else get(BASE + "/")
    items = parse_list(listing)
    print(f"Omnia: {len(items)} jobs on the careers page", file=sys.stderr)
    rows = []
    today = datetime.date.today().isoformat()
    for it in items:
        if it["country"] and it["country"].lower() != "south africa":
            print(f"  skip (outside SA): {it['title']} - {it['city']}, {it['country']}", file=sys.stderr)
            continue
        try:
            if from_dir:
                f = os.path.join(from_dir, it["id"] + ".html")
                if not os.path.exists(f):
                    continue
                page = open(f, encoding="utf-8").read()
            else:
                page = get(f"{BASE}/jobs/{it['id']}")
                time.sleep(1)
            row = build_row(it, page, columns)
        except Exception as e:
            print(f"  skipped {it['title']}: {e}", file=sys.stderr)
            continue
        if not row["responsibilities"] or not row["requirements"]:
            print(f"  skipped (could not read duties/requirements): {it['title']}", file=sys.stderr)
            continue
        if row["closing_date"] and row["closing_date"] < today:
            continue
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-dir")
    a = ap.parse_args()
    try:
        rows = scrape(a.from_dir)
    except Exception as e:                       # never fail the daily run
        print(f"Omnia: could not read the careers page ({e})", file=sys.stderr)
        return
    if a.dry_run or a.from_dir:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        print(f"{len(rows)} jobs", file=sys.stderr)
        return
    import sheet_writer
    new, upd = sheet_writer.upsert_jobs(rows, update_fields=("closing_date", "about_role", "responsibilities", "requirements"))
    print(f"Omnia: found {len(rows)}, wrote {new} new, updated {upd}.", file=sys.stderr)


if __name__ == "__main__":
    main()
