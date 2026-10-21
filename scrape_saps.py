#!/usr/bin/env python3
"""
scrape_saps.py  —  OnboardingSA

South African Police Service vacancies, from two official places:

  1. SAPS careers pages (www.saps.gov.za/careers/...): tables of
     Job Title | Remuneration | Location | Closing Date, each title linking to the
     advert PDF. The PDF is read for requirements, duties and how to apply.
  2. SAPS e-Recruitment portal (erecruitment.saps.gov.za/SAPS-Vacancies/): the
     job list loads from a JSON feed; each job has its own detail page.

A job that appears in both (same reference number, e.g. the Police Trainee
advert TRA26/27) is kept once: the PDF's full text, with the portal as the
apply link.

www.saps.gov.za serves an incomplete certificate chain that ordinary HTTP
clients reject, so everything is fetched through Chromium (which completes the
chain itself) — certificate checking stays on.

Not published: the "Enquiries" blocks (named officers and their direct numbers).

    python3 scrape_saps.py             # scrape and write new rows to the sheet
    python3 scrape_saps.py --dry-run   # print rows as JSON instead
"""

import argparse, base64, datetime, hashlib, html, json, os, re, subprocess, sys, tempfile, time
from urllib.parse import urljoin

from scrape_dpsa import title_case, guess_category, find_province, short_salary, summary_line, norm_ws

EMPLOYER = "South African Police Service"
CAREERS = "https://www.saps.gov.za/careers/"
CAREER_PAGES = ["ptrainees.php", "publicact.php", "ls.php", "smanagement.php",
                "internships.php", "pserviceact.php", "reenlisments.php"]   # plus any found on careers.php
ERECRUIT = "https://erecruitment.saps.gov.za"
ERECRUIT_LIST = ERECRUIT + "/SAPS-Vacancies/"
ERECRUIT_DETAIL = ERECRUIT + "/View-Full-Vacancy/?id="

TODAY = datetime.date.today().isoformat()
OFFICIAL_MAILBOX = re.compile(r"appoint|recruit|vacanc|career|job|applica|hr\b|human", re.I)
RANK = (r"(?:Lt\.?|Lieutenant|Major|Brigadier|Colonel|Col\.?|Captain|Capt\.?|Warrant\s+Officer|W/O|Sergeant|Sgt\.?|"
        r"Constable|Const\.?|General|Gen\.?|Mr|Mrs|Ms|Miss|Dr)")


# ----------------------------------------------------------------- careers tables

def strip_comments(h):
    return re.sub(r"<!--.*?-->", "", h or "", flags=re.S)


def cell_text(c):
    return norm_ws(html.unescape(re.sub(r"<[^>]+>", " ", c)))


def parse_table_rows(page_html, page_url):
    """Rows of the careers job tables. Commented-out rows are ignored."""
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", strip_comments(page_html), re.S | re.I):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
        if len(cells) < 4:
            continue
        link = re.search(r'href="([^"]+\.pdf)"', cells[0], re.I)
        m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", cell_text(cells[3]))
        if not link or not m:
            continue
        rows.append({
            "title": cell_text(cells[0]),
            "pdf": urljoin(page_url, link.group(1).strip()).replace(" ", "%20"),
            "pay": cell_text(cells[1]),
            "location": cell_text(cells[2]),
            "closing": f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
            "page": page_url,
        })
    return rows


def career_page_links(careers_html):
    out = []
    for h in re.findall(r'href="([^"#?]+\.php)"', strip_comments(careers_html)):
        h = h.replace("../careers/", "").replace("/careers/", "")
        if "/" not in h and h not in out and h != "careers.php":
            out.append(h)
    return out


# ----------------------------------------------------------------- advert PDFs

SECTION_HEADS = [
    ("req",   r"Generic appointment requirements[^\n]*:?"),
    ("req",   r"Additional Post Requirements\s*:?"),
    ("req",   r"APPOINTMENT REQUIREMENTS\s*:?"),
    ("req",   r"QUALIFICATIONS\s*:"),
    ("req",   r"GENERIC REQUIREMENTS[^\n]*"),
    ("skip",  r"SELECTION PROCESS\s*:"),
    ("skip",  r"The following generic competencies[^\n]*:?"),
    ("duty",  r"Core Responsibilities\s*:?"),
    ("duty",  r"Core Functions\s*:?"),
    ("duty",  r"CORE FUNCTIONS\s*:?"),
    ("general", r"GENERAL(?: INFORMATION)?\s*:"),
    ("general", r"General\s*:"),
    ("enq",   r"[➢\s]*Enquiries can be directed to\s*:?"),
    ("apply", r"[➢\s]*Applications must be (?:posted|hand delivered)[^\n]*"),
    ("apply", r"NATIONAL OFFICE\s*:"),
    ("apply", r"[^\n]*following e-mail addresses\s*:"),
    ("apply", r"Application forms may be delivered by hand[^\n]*"),
    ("apply", r"[❖\s]*NB: To apply online[^\n]*"),
]
HEAD_RE = re.compile(r"^[ \t\f•·➢❖\-]*(" + "|".join(p for _, p in SECTION_HEADS) + r")", re.M)


def _section_kind(head):
    for kind, pat in SECTION_HEADS:
        if re.match(r"[ \t\f•·➢❖\-]*" + pat, head):
            return kind
    return None


def split_sections(text):
    """{'req': [...], 'duty': [...], 'general': [...], 'apply': [...], 'enq': [...]} of raw text blocks."""
    out = {}
    marks = [(m.start(), m.end(), _section_kind(m.group(0))) for m in HEAD_RE.finditer(text)]
    for i, (s, e, kind) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        block = text[s:end] if kind == "apply" else text[e:end]
        if kind == "apply" and "To apply online" in block:
            block = block.split("❖", 2)[1] if block.count("❖") >= 2 else block   # trainee: just the online step
        out.setdefault(kind, []).append(block)
    return out


def to_items(block):
    """Bulleted / dashed / wrapped PDF text -> list of clean one-line items."""
    block = re.sub(r"\n\s*-\s*\d+\s*-\s*\n", "\n", block)              # page numbers "-2-"
    lines = [l.rstrip() for l in block.splitlines()]
    items, cur = [], ""
    for l in lines:
        s = l.strip()
        if not s:
            if cur: items.append(cur); cur = ""
            continue
        if re.match(r"^[•·➢❖✓\-–\*]\s*", s) or re.match(r"^\(?[a-z0-9]{1,2}[.)]\s+", s):
            if cur: items.append(cur)
            cur = re.sub(r"^[•·➢❖✓\-–\*]\s*|^\(?[a-z0-9]{1,2}[.)]\s+", "", s)
        else:
            cur = (cur + " " + s).strip() if cur else s
    if cur: items.append(cur)
    split = []
    for it in items:
        split += re.split(r";\s+(?=[A-Z])", it)
    clean = []
    for it in split:
        it = norm_ws(it).strip(" ;,")
        it = re.sub(r"\s*;?\s*and$", "", it)
        if len(it) < 4 or re.fullmatch(r"Applicants\s*:?", it, re.I):
            continue
        clean.append(it[:1].upper() + it[1:])
    return clean


def header_fields(text):
    """Field lines at the top of an advert ('POST:', 'Post title:', 'Salary Level:' ...)."""
    keys = {"post": r"POST|Post title", "location": r"LOCATION|Component",
            "pay": r"LEVEL OF REMUNERATION|Salary Level|Remuneration",
            "ref": r"REFERENCES?|Ref(?:erence)? Number|Reference"}
    head = text[:1500]
    out = {}
    lab = re.compile(r"^\s*(" + "|".join(keys.values()) + r")\s*:\s*(.*)$", re.M | re.I)
    found = list(lab.finditer(head))
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else head.find("\n\n", m.end())
        val = head[m.start(2): end if end > 0 else m.end()]
        val = norm_ws(val.replace("\n", " "))
        for k, pat in keys.items():
            if k == "ref" and re.fullmatch(pat, m.group(1), re.I):
                val = norm_ws(m.group(2))
            if re.fullmatch(pat, m.group(1), re.I) and k not in out:
                out[k] = val
    return out


def _columns(block):
    """Two side-by-side columns in PDF text -> left column, then right column."""
    left, right = [], []
    for l in block.splitlines():
        parts = re.split(r"\s{3,}", l.strip(), maxsplit=1)
        if len(parts) == 2 and len(l) - len(l.lstrip()) < 20:
            left.append(parts[0]); right.append(parts[1])
        elif len(l) - len(l.lstrip()) >= 30:
            right.append(l.strip())
        else:
            left.append(l.strip())
    return "\n".join(left + ([""] if right else []) + right)


def clean_apply(block):
    """How-to-apply text without officer names, phone numbers or personal mailboxes."""
    lines = []
    for l in _columns(block).splitlines():
        s = norm_ws(l)
        if not s or re.fullmatch(r"-\s*\d+\s*-|\d{1,3}", s):
            continue
        s = s.lstrip("➢❖•· ")
        if re.match(RANK + r"\b", s) or re.search(r"\b" + RANK + r"\s+[A-Z]{1,3}\s+[A-Z][a-z]+", s):
            continue
        if re.match(r"Enquiries", s, re.I):
            continue                                         # "Lt Colonel ME Mokholoane / Captain KM Sereetsi"
        if re.search(r"(?:Tel|Cell)\b|\(0\d{2}\)|\b0[6-8]\d[\s-]?\d{3}[\s-]?\d{4}\b", s):
            continue
        s = re.sub(r"[\w.+-]+@[\w.-]+", lambda m: m.group(0) if OFFICIAL_MAILBOX.search(m.group(0).split("@")[0]) else "", s)
        if norm_ws(s):
            lines.append(norm_ws(s))
    text = " ".join(lines)
    text = re.sub(r"\s{2,}", " ", text).strip(" :")
    # drop any sentence that names an officer or carries extension numbers
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    sents = [x for x in sents if not re.search(r"\b" + RANK + r"\.?\s+[A-Z][a-z]+|\b\d{4}\s*/\s*\d{4}\b", x)]
    text = " ".join(sents)
    text = re.sub(r"^following e-mail addresses\s*:", "Email your application to:", text, flags=re.I)
    return text


GENERIC_HEAD = re.compile(r"^[ \t\f•·➢❖\-]*([A-Za-z][A-Za-z ,&/()'’\-]{2,70}?)\s*:?\s*$", re.M)
INLINE_HEAD = re.compile(r"^[ \t\f•·➢❖\-]*([A-Z][A-Za-z ,&/()'’\-]{2,50}?)\s*:\s+(\S.*)$", re.M)
REQ_WORDS = re.compile(r"requirement|qualification|competenc|knowledge|skills|experience|eligib|criteria", re.I)
DUTY_WORDS = re.compile(r"dut(?:y|ies)|function|responsibilit|key performance|\bKPAs?\b|job purpose|tasks|outputs", re.I)
STOP_WORDS = re.compile(r"general|note|enquir|application|how to apply|closing|contact|correspondence|remuneration|salary", re.I)


def fallback_sections(text):
    """Unknown layout: find headings by their wording ('Minimum Requirements', 'Key Performance Areas'...)."""
    heads = []
    for m in INLINE_HEAD.finditer(text):                   # "REQUIREMENTS: Applicants must ..." on one line
        h = m.group(1).strip()
        if len(h.split()) > 5:
            continue
        kind = ("duty" if DUTY_WORDS.search(h) else "req" if REQ_WORDS.search(h)
                else "stop" if STOP_WORDS.search(h) else None)
        if kind:
            heads.append((m.start(), m.start(2), kind))
    for m in GENERIC_HEAD.finditer(text):
        h = m.group(1).strip()
        line = m.group(0).strip()
        if not (line.endswith(":") or h.isupper()) or len(h.split()) > 8:
            continue
        kind = ("duty" if DUTY_WORDS.search(h) else "req" if REQ_WORDS.search(h)
                else "stop" if STOP_WORDS.search(h) else None)
        if kind:
            heads.append((m.start(), m.end(), kind))
    heads.sort()
    out = {"req": [], "duty": []}
    for i, (s_, e, kind) in enumerate(heads):
        if kind in out:
            end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
            for it in to_items(text[e:end]):               # paragraphs -> one item per sentence
                out[kind] += [x.strip() for x in re.split(r"(?<=[a-z0-9)])\.\s+(?=[A-Z])", it) if len(x.strip()) > 3] \
                    if len(it) > 200 else [it]
    return out


def parse_advert(text):
    """Structured fields from a SAPS advert PDF's text."""
    hdr = header_fields(text)
    sec = split_sections(text)
    req = [i for b in sec.get("req", []) for i in to_items(b)]
    duty = [i for b in sec.get("duty", []) for i in to_items(b)]
    if not duty:                                           # trainee advert
        m = re.search(r"following functions\s*:(.*?)(?:\n\s*[A-Z][A-Z]{3,}[A-Z ]*[:(]|\Z)", text, re.S)
        if m:
            duty = to_items(m.group(1))
    if text and (not req or not duty):                     # layout not recognised: read by heading wording
        fb = fallback_sections(text)
        req = req or fb["req"]
        duty = duty or fb["duty"]
    apply = " ".join(x for x in [clean_apply(b) for b in sec.get("apply", []) + sec.get("enq", [])] if x)
    closing = re.search(r"closing date (?:for applications )?is\s*:?\s*([^.\n]+)|Closing date for applications\s*:\s*([^\n]+)",
                        text, re.I)
    ref = hdr.get("ref") or ""
    m = re.search(r"Reference\s*:\s*([A-Z0-9/]+)", text)
    if not ref and m:
        ref = m.group(1)
    count = re.search(r"\((\d+)\s*posts?\)", ref, re.I)
    ref_clean = re.sub(r"^Post\s+No\.?\s*", "", re.sub(r"\(.*?\)", "", ref)).strip(" .,;")
    return {
        "post": hdr.get("post", ""), "location": hdr.get("location", ""), "pay": hdr.get("pay", ""),
        "ref": ref_clean, "count": int(count.group(1)) if count else 1,
        "requirements": req, "duties": duty, "apply": apply,
        "closing_text": norm_ws(next((g for g in (closing.groups() if closing else []) if g), "")),
        "no_email": bool(re.search(r"No email option", text, re.I)),
        "online": bool(re.search(r"apply online|electronic recruitment|e-?recruitment", text, re.I)),
    }


# ----------------------------------------------------------------- e-Recruitment

def parse_grid(records):
    out = []
    for r in records:
        a = {x["Name"]: (x.get("FormattedValue") or x.get("Value")) for x in r.get("Attributes", [])}
        out.append({"id": r.get("Id"), "name": a.get("saps_vacancyname", ""), "ref": a.get("saps_vacancyreference", ""),
                    "type": a.get("saps_employementtype", ""), "where": a.get("saps_governmentspheres", ""),
                    "start": a.get("saps_validityperiodstart", ""), "end": a.get("saps_validityperiodend", ""),
                    "openings": a.get("saps_openings", ""), "status": a.get("saps_advertstatus", "")})
    return out


def us_date(s):
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s or "")
    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else ""


def parse_erecruit_detail(page_html):
    h = page_html
    title = re.search(r'class="saps-vd-title"[^>]*>(.*?)<', h, re.S)
    labels = {m.group(1): cell_text(m.group(2)) for m in re.finditer(r'data-label="([^"]+)"[^>]*>(.*?)</div>', h, re.S)}
    blocks = {m.group(1): cell_text(m.group(2)) for m in re.finditer(r'data-block="([^"]+)"[^>]*>(.*?)</div>', h, re.S)
              if "'" not in m.group(1)}
    closing = re.search(r'data-closing-date="([\d-]+)"', h)
    openings = re.search(r'data-openings="(\d+)"', h)
    star = lambda t: [x.strip(" ;.") for x in re.split(r"\s*\*\s*", t or "") if len(x.strip(" ;.")) > 3]
    return {"title": cell_text(title.group(1)) if title else "", "labels": labels,
            "requirements": star(blocks.get("generic requirement")) + star(blocks.get("additional requirement")),
            "duties": star(blocks.get("core function")),
            "closing": closing.group(1) if closing else "", "openings": openings.group(1) if openings else ""}


# ----------------------------------------------------------------- rows

def nice_date(iso):
    try:
        return datetime.date.fromisoformat(iso).strftime("%-d %B %Y")
    except Exception:
        return iso


def job_id(ref, fallback):
    key = re.sub(r"[^A-Za-z0-9]+", "-", ref or "").strip("-")
    return "SAPS-" + (key or hashlib.sha1(fallback.encode()).hexdigest()[:10]).upper()


def saps_category(title, page):
    if "/ls.php" in page or re.search(r"\blegal\b|litigation", title, re.I):
        return "Legal"
    if "/smanagement" in page:
        return "Management"
    return "Security"            # police posts (SAPS Act), trainees included


def intro_line(title, count, location, emp_type, pay):
    national = not location or re.fullmatch(r"national(?: level)?|head office", location.strip(), re.I)
    s = summary_line(EMPLOYER, title, count, "" if national else location, emp_type, pay, "")
    s = re.sub(r"^South African Police Service", "The South African Police Service", s)
    return s.replace(".", " (national post).", 1) if national and " based in " not in s else s


def build_careers_row(r, ad):
    title = norm_ws(re.sub(r"\s*\(at the level of [^)]*\)", "", r["title"], flags=re.I)) or title_case(ad["post"])
    dup = re.fullmatch(r"(.+?)\s+\1s?", title, re.I)            # "Police Trainee Police Trainees"
    if dup:
        title = dup.group(1)
    rank = re.search(r"\(at the level of ([^)]*)\)", r["title"], re.I)
    if ad["location"] and "/smanagement" not in r["page"]:
        parts = [x.strip() for x in ad["location"].split(",") if x.strip()]
        location = ", ".join(parts[-2:])                         # "..., Durban, KwaZulu-Natal"
    else:
        location = r["location"]
    province = find_province(location, r["location"]) or ("National" if re.search(r"national", r["location"], re.I) else "")
    pay = short_salary(ad["pay"] or r["pay"]) or r["pay"]
    is_trainee = bool(re.search(r"trainee", r["title"], re.I))
    emp_type = "Contract" if is_trainee else "Permanent"
    about = [intro_line(title, ad["count"], location, emp_type, ad["pay"] or r["pay"])]
    if rank:
        about.append(f"Rank: {rank.group(1).strip()}.")
    about.append("")
    if ad["apply"]:
        about.append("How to apply: " + ad["apply"])
    if ad["ref"]:
        about.append("Reference number to quote: " + ad["ref"])
    ct = ad["closing_text"].strip(" .")
    about.append("Closing date: " + (nice_date(ct) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", ct) else ct or nice_date(r["closing"])))
    about.append("Use the official SAPS application form (the Z83 is not accepted), attach a CV and the documents listed in the advert."
                 if not is_trainee else "Apply on the SAPS e-Recruitment portal or as set out in the advert.")
    return {
        "id": job_id(ad["ref"], r["pdf"]), "job_title": title, "employer": EMPLOYER,
        "category": saps_category(title, r["page"]),
        "province": province or "National", "location": norm_ws(location)[:140],
        "employment_type": emp_type, "salary": pay, "posted_date": TODAY, "closing_date": r["closing"],
        "reference_no": job_id(ad["ref"], r["pdf"]), "about_role": "\n".join(about),
        "responsibilities": "\n".join(ad["duties"]), "requirements": "\n".join(ad["requirements"]),
        # adverts that say "apply online" point to the e-Recruitment portal (the job page there, once matched)
        "official_apply_url": ERECRUIT_LIST if ad.get("online") else r["pdf"],
        "source_url": r["page"], "featured": "", "status": "live",
        "_ref": ad["ref"],
    }


def build_erecruit_row(g, d):
    labels = d["labels"]
    ref = labels.get("Reference Number") or g["ref"]
    title = title_case(re.sub(r"\s*-\s*" + re.escape(ref) + r"\s*$", "", d["title"] or g["name"])) if ref else title_case(d["title"] or g["name"])
    pay = labels.get("Salary") or labels.get("Stipend") or labels.get("Remuneration") or ""
    emp_type = labels.get("Employment Type") or g["type"] or ""
    location = labels.get("Location") or g["where"]
    count = int(d["openings"] or g["openings"] or 1)
    if labels.get("Stipend") and not re.search(r"month|annum|year", pay, re.I):
        pay += " per month"
    about = [intro_line(title, count, location, emp_type, pay), "",
             "How to apply: online on the SAPS e-Recruitment portal (erecruitment.saps.gov.za).",
             "Reference number to quote: " + ref, "Closing date: " + nice_date(d["closing"] or us_date(g["end"]))]
    return {
        "id": job_id(ref, g["id"]), "job_title": title, "employer": EMPLOYER,
        "category": saps_category(title, ""),
        "province": find_province(location) or "National", "location": location,
        "employment_type": emp_type, "salary": short_salary(pay) or pay, "posted_date": us_date(g["start"]) or TODAY,
        "closing_date": d["closing"] or us_date(g["end"]), "reference_no": job_id(ref, g["id"]),
        "about_role": "\n".join(about), "responsibilities": "\n".join(d["duties"]),
        "requirements": "\n".join(d["requirements"]), "official_apply_url": ERECRUIT_DETAIL + g["id"],
        "source_url": ERECRUIT_LIST, "featured": "", "status": "live", "_ref": ref,
    }


def merge(careers_rows, erecruit_rows):
    """One row per reference number: PDF detail + portal apply link."""
    by_ref = {re.sub(r"\W", "", r["_ref"]).upper(): r for r in careers_rows if r["_ref"]}
    out = list(careers_rows)
    for e in erecruit_rows:
        key = re.sub(r"\W", "", e["_ref"]).upper()
        if key and key in by_ref:
            c = by_ref[key]
            c["official_apply_url"] = e["official_apply_url"]
            c["about_role"] = c["about_role"].replace(
                "Apply on the SAPS e-Recruitment portal or as set out in the advert.",
                "Apply online on the SAPS e-Recruitment portal (erecruitment.saps.gov.za).")
        else:
            out.append(e)
    seen, final = set(), []
    for r in out:
        if r["id"] in seen or r["closing_date"] < TODAY:
            continue
        seen.add(r["id"]); r.pop("_ref", None); final.append(r)
    return final


# ----------------------------------------------------------------- browser fetching

FETCH_JS = """async u => { const r = await fetch(u); if (!r.ok) throw new Error('HTTP ' + r.status);
  const b = new Uint8Array(await r.arrayBuffer()); let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
  return btoa(s); }"""


def retry(fn, tries=3, wait=10):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            print(f"  retry {i + 1}/{tries}: {str(e)[:120]}", file=sys.stderr)
            time.sleep(wait)
    return None


def pdf_text(data):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
    try:
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
    finally:
        os.unlink(f.name)


def scrape_careers(pg):
    rows = []
    def goto(u):
        pg.goto(u, wait_until="load", timeout=180000)
        return pg.content()
    home = retry(lambda: goto(CAREERS + "careers.php")) or ""
    pages = CAREER_PAGES + [p for p in career_page_links(home) if p not in CAREER_PAGES]
    table_rows = []
    for name in pages:
        h = retry(lambda: goto(CAREERS + name))
        if h:
            try:
                found = parse_table_rows(h, CAREERS + name)
            except Exception as e:
                print(f"  {name}: could not read table: {str(e)[:150]}", file=sys.stderr)
                continue
            print(f"  {name}: {len(found)} open rows", file=sys.stderr)
            table_rows += [r for r in found if r["closing"] >= TODAY]
    for r in table_rows:
        try:
            b64 = retry(lambda: pg.evaluate(FETCH_JS, r["pdf"]))
            if not b64:
                print(f"  skipped (advert would not download, retry tomorrow): {r['title']}", file=sys.stderr)
                continue
            ad = parse_advert(pdf_text(base64.b64decode(b64)))
            if not ad["requirements"] or not ad["duties"]:
                print(f"  skipped (advert layout not readable): {r['title']} — {r['pdf']}", file=sys.stderr)
                continue
            rows.append(build_careers_row(r, ad))
        except Exception as e:
            print(f"  skipped (error): {r['title']}: {str(e)[:150]}", file=sys.stderr)
    return rows


def scrape_erecruit(pg):
    """The portal never goes fully quiet, so wait for its job-list feed instead of for the page to settle."""
    grids = []
    pg.on("response", lambda resp: grids.append(resp) if "entity-grid-data.json" in resp.url else None)
    def load():
        with pg.expect_response(lambda r: "entity-grid-data.json" in r.url, timeout=240000):
            pg.goto(ERECRUIT_LIST, wait_until="domcontentloaded", timeout=240000)
        return True
    if not retry(load, tries=3, wait=20) and not grids:
        print("  e-Recruitment did not answer today", file=sys.stderr)
        return []
    pg.wait_for_timeout(3000)
    recs = []
    for resp in grids:
        try:
            recs += parse_grid(resp.json().get("Records", []))
        except Exception:
            pass
    rows = []
    for g in {r["id"]: r for r in recs if r["id"]}.values():
        def detail():
            pg.goto(ERECRUIT_DETAIL + g["id"], wait_until="load", timeout=240000)
            pg.wait_for_selector(".saps-vd-title", timeout=120000)
            return pg.content()
        h = retry(detail, tries=2)
        if not h:
            continue
        try:
            d = parse_erecruit_detail(h)
            if not d["requirements"] or not d["duties"]:
                print(f"  skipped (portal page layout not readable): {g['name']}", file=sys.stderr)
                continue
            rows.append(build_erecruit_row(g, d))
        except Exception as e:
            print(f"  skipped (error): {g['name']}: {str(e)[:150]}", file=sys.stderr)
    print(f"  e-Recruitment: {len(rows)} vacancies", file=sys.stderr)
    return rows


def scrape():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        careers, erecruit = [], []
        try:
            careers = scrape_careers(pg)
        except Exception as e:
            print(f"SAPS careers pages failed today: {str(e)[:200]}", file=sys.stderr)
        try:
            erecruit = scrape_erecruit(b.new_page())
        except Exception as e:
            print(f"SAPS e-Recruitment failed today: {str(e)[:200]}", file=sys.stderr)
        b.close()
    return merge(careers, erecruit)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    rows = scrape()
    if a.dry_run:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=1)
        print(f"\n{len(rows)} SAPS posts", file=sys.stderr)
        return
    import sheet_writer
    wrote, updated = sheet_writer.upsert_jobs(rows, update_fields=("official_apply_url", "closing_date", "about_role"))
    print(f"SAPS: {len(rows)} open posts, {wrote} new rows, {updated} existing rows updated.", file=sys.stderr)


if __name__ == "__main__":
    main()
