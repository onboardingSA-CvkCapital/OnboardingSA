#!/usr/bin/env python3
"""
scrape_dpsa.py  —  OnboardingSA

Reads the DPSA Public Service Vacancy Circular (published weekly at
https://www.dpsa.gov.za/newsroom/psvc/) and writes one row per post to the
Jobs sheet, in the same columns every other scraper uses.

How it works
  1. Open the circular index and take the newest few circulars
     (older ones have closed; the sheet de-duplicates anything already saved).
  2. On each circular page, collect the per-department PDFs (a.pdf, b.pdf ...).
  3. Convert each PDF to text with `pdftotext -layout` (poppler-utils) and split
     it into posts using the standard field labels (POST, SALARY, CENTRE,
     REQUIREMENTS, DUTIES, ENQUIRIES, APPLICATIONS, NOTE, CLOSING DATE ...).
  4. Map each post to the sheet columns. ENQUIRIES (named officials and their
     direct phone numbers) is deliberately not published.

Runs daily from the GitHub workflow. Test locally against a downloaded PDF:

    python3 scrape_dpsa.py --pdf "PSV CIRCULAR 35 of 2026.pdf" --dry-run
"""

import argparse, datetime, html, json, os, re, subprocess, sys, tempfile, time
from urllib.parse import urljoin

BASE = "https://www.dpsa.gov.za"
INDEX_URL = BASE + "/newsroom/psvc/"
CIRCULARS_TO_CHECK = 3          # newest N circulars; posts usually close within ~2 weeks
UA = {"User-Agent": "Mozilla/5.0 (compatible; OnboardingSA job board; +https://www.onboardingsa.co.za)"}

PROVINCES = ["Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo",
             "Mpumalanga", "North West", "Northern Cape", "Western Cape"]

# Towns that often appear in CENTRE lines without a province name.
TOWN_PROVINCE = {
    "pretoria": "Gauteng", "tshwane": "Gauteng", "johannesburg": "Gauteng", "midrand": "Gauteng",
    "centurion": "Gauteng", "soweto": "Gauteng", "germiston": "Gauteng", "benoni": "Gauteng",
    "vereeniging": "Gauteng", "krugersdorp": "Gauteng", "randburg": "Gauteng", "boksburg": "Gauteng",
    "durban": "KwaZulu-Natal", "pietermaritzburg": "KwaZulu-Natal", "richards bay": "KwaZulu-Natal",
    "newcastle": "KwaZulu-Natal", "ladysmith": "KwaZulu-Natal", "ulundi": "KwaZulu-Natal",
    "port shepstone": "KwaZulu-Natal", "empangeni": "KwaZulu-Natal", "ethekwini": "KwaZulu-Natal",
    "cape town": "Western Cape", "bellville": "Western Cape", "george": "Western Cape",
    "stellenbosch": "Western Cape", "paarl": "Western Cape", "worcester": "Western Cape",
    "oudtshoorn": "Western Cape", "elsenburg": "Western Cape", "malmesbury": "Western Cape",
    "gqeberha": "Eastern Cape", "port elizabeth": "Eastern Cape", "east london": "Eastern Cape",
    "mthatha": "Eastern Cape", "bhisho": "Eastern Cape", "makhanda": "Eastern Cape",
    "komani": "Eastern Cape", "queenstown": "Eastern Cape", "middelburg (ec)": "Eastern Cape",
    "bloemfontein": "Free State", "welkom": "Free State", "botshabelo": "Free State",
    "ficksburg": "Free State", "bethlehem": "Free State", "kroonstad": "Free State",
    "polokwane": "Limpopo", "giyani": "Limpopo", "thohoyandou": "Limpopo", "tzaneen": "Limpopo",
    "lephalale": "Limpopo", "makhado": "Limpopo", "mokopane": "Limpopo", "seshego": "Limpopo",
    "lebowakgomo": "Limpopo", "phalaborwa": "Limpopo", "modimolle": "Limpopo",
    "groblersdal": "Limpopo", "jane furse": "Limpopo",
    "mbombela": "Mpumalanga", "nelspruit": "Mpumalanga", "emalahleni": "Mpumalanga",
    "witbank": "Mpumalanga", "secunda": "Mpumalanga", "ermelo": "Mpumalanga",
    "mahikeng": "North West", "mafikeng": "North West", "rustenburg": "North West",
    "klerksdorp": "North West", "potchefstroom": "North West", "vryburg": "North West",
    "kimberley": "Northern Cape", "upington": "Northern Cape", "springbok": "Northern Cape",
    "de aar": "Northern Cape", "kuruman": "Northern Cape",
}

FIELD_LABELS = {
    "SALARY": "salary", "STIPEND": "stipend", "CENTRE": "centre",
    "REQUIREMENTS": "requirements", "DUTIES": "duties", "DUTES": "duties",
    "ENQUIRIES": "enquiries", "EENQUIRIES": "enquiries", "ENQUIRY": "enquiries",
    "APPLICATIONS": "applications", "APPLICATION": "applications",
    "NOTE": "note", "NOTES": "note", "CLOSING DATE": "closing",
    "FOR ATTENTION": "attention", "ATTENTION": "attention",
}
LABEL_RE = re.compile(r"^\s*(" + "|".join(sorted(map(re.escape, FIELD_LABELS), key=len, reverse=True))
                      + r")\s*:\s?(.*)$")
POST_RE = re.compile(r"^\s*POST\s+(\d{1,2})\s*/\s*(\d{1,3})\s*:?\s*(.*)$")
ANNEX_RE = re.compile(r"^\s*ANNEXURE\s+([A-Z]{1,2})\s*$")
PROVADMIN_RE = re.compile(r"^\s*PROVINCIAL ADMINISTRATION\s*:\s*([A-Z][A-Z \-]+?)\s*$")
PAGE_NO_RE = re.compile(r"^\s*\d{1,3}\s*$")
SECTION_RE = re.compile(r"^\s*(OTHER POSTS?|MANAGEMENT ECHELON|SENIOR MANAGEMENT SERVICE|"
                        r"GRADUATE INTERNSHIP PROGRAMME|INTERNSHIP PROGRAMME|LEARNERSHIP.*)\s*$")
DEPT_RE = re.compile(r"^\s*((?:DEPARTMENT|OFFICE|NATIONAL|PROVINCIAL TREASURY|GOVERNMENT|POLICE|"
                     r"INDEPENDENT|STATISTICS|WESTERN CAPE|GAUTENG|COMMISSION|THE PRESIDENCY|"
                     r"STATE|PUBLIC|SOUTH AFRICAN|CIVILIAN|MILITARY)[A-Z ,&()\-'’]*)\s*$")
REF_RE = re.compile(r"REF(?:ERENCE)?\.?\s*(?:NO|NUMBER)\.?\s*:?\s*"
                    r"([A-Z0-9][A-Z0-9/.\-_]*(?:\s[A-Z0-9/.\-_]*[0-9/][A-Z0-9/.\-_]*)*)", re.I)
COUNT_RE = re.compile(r"\(\s*X?\s*(\d+)\s*POSTS?\s*\)", re.I)
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                      "august", "september", "october", "november", "december"], 1)}

CATEGORY_RULES = [
    ("Internship", r"\bintern|learner|graduate programme|trainee"),
    ("Medical", r"nurse|nursing|medical|doctor|pharmac|clinical|radiograph|physiotherap|dietitian|"
                r"dental|health|emergency care|psycholog|occupational therap|speech|audiolog|optometr"),
    ("Legal", r"legal|attorney|advocate|prosecutor|magistrate|law\b|litigation|court"),
    ("IT", r"\bict\b|information technology|software|network|systems? admin|programmer|developer|"
           r"\bit\b|cyber|data(base)? |business intelligence"),
    ("Engineering", r"engineer|technician|technologist|artisan|electrician|plumber|mechanic|"
                    r"draughts|surveyor|built environment|infrastructure|architect"),
    ("Finance", r"financ|account|audit|budget|treasury|revenue|supply chain|procurement|"
                r"payroll|asset|bookkeep|economist|salar"),
    ("Education", r"educator|teacher|lecturer|principal|education|curriculum|training"),
    ("Social Services", r"social work|social auxiliary|community development|child and youth care|"
                        r"probation"),
    ("Agriculture", r"agricultur|veterinar|animal|farm|crop|soil|forestry|fisheries|environment"),
    ("Security", r"security|safety|correctional|police|traffic|law enforcement|firefight"),
    ("HR", r"human resource|\bhr\b|labour relations|employee relations|recruitment|"
           r"skills development|personnel"),
    ("Admin", r"admin|clerk|secretary|registry|receptionist|office aid|messenger|typist|"
              r"data captur|personal assistant|executive assistant|records"),
    ("Management", r"director|manager|head of|chief executive|deputy director"),
    ("General Worker", r"cleaner|general worker|driver|food service|porter|gardener|handyman|"
                       r"groundsman|laundry|housekeep|cook|tradesman aid"),
]


# ----------------------------------------------------------------- helpers

def norm_ws(s):
    return re.sub(r"[ \t\u00a0]+", " ", (s or "").replace("`", " ")).strip()


def join_lines(lines):
    """Join wrapped PDF lines into readable text, fixing hyphenated breaks."""
    out = ""
    for ln in (norm_ws(l) for l in lines):
        if not ln:
            continue
        if not out:
            out = ln
        elif out.endswith("-") and not out.endswith(" -") and ln[:1].islower():
            out = out[:-1] + ln            # "pre-" + "entry"  -> "pre-entry"? keep simple: re-join word
        else:
            out += " " + ln
    return out.strip()


def title_case(s):
    small = {"and", "of", "the", "in", "for", "to", "on", "at", "an", "or", "with", "by"}
    words = []
    for i, w in enumerate(s.lower().split()):
        if w.upper().strip("()[],.:;") in {"MIS", "ECM", "CHC", "CDC", "TVET", "NQF", "ICT", "HR", "IT", "UIF", "SMS", "EE", "PPP", "CEO", "CFO", "SCM", "GIS",
                         "OSD", "PHC", "ICU", "TB", "HIV", "NSG", "SAPS", "ECD", "MEC", "DDG",
                         "IPD", "EMS", "EHP", "PA", "UI"}:
            words.append(w.upper())
        elif i and w in small:
            words.append(w)
        else:
            words.append(w[:1].upper() + w[1:] if not w[:1] in "(\"'" else w[:2].upper() + w[2:])
    return " ".join(words)


def parse_date(text):
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]+)\s+(\d{4})", text or "")
    if not m or m.group(2).lower() not in MONTHS:
        return ""
    try:
        return datetime.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
    except ValueError:
        return ""


def find_province(*texts, default=""):
    for t in texts:
        low = (t or "").lower().replace("kwazulu natal", "kwazulu-natal")
        for p in PROVINCES:
            if p.lower() in low:
                return p
    for t in texts:
        low = (t or "").lower()
        for town, p in TOWN_PROVINCE.items():
            if re.search(r"\b" + re.escape(town) + r"\b", low):
                return p
    return default


def guess_category(title, dept):
    t = (title or "").lower()
    for cat, pat in CATEGORY_RULES:
        if re.search(pat, t):
            return cat
    return "Government"


def employment_type(text):
    t = (text or "").lower()
    if re.search(r"intern|learnership|graduate programme|trainee", t):
        return "Internship"
    if re.search(r"contract|fixed[- ]term|\d+\s*(months|years?)\b", t):
        return "Contract"
    if "part-time" in t or "part time" in t:
        return "Part-time"
    return "Permanent"


def clean_dept(name):
    name = norm_ws(name).strip(" :")
    name = re.sub(r"\s*\((?:[A-Z]{2,8})\)\s*$", "", name)          # "(DOA)"
    return title_case(name)


# ----------------------------------------------------------------- parsing

def split_posts(text):
    """Yield raw post dicts from layout text of a circular or one department PDF."""
    lines = text.splitlines()
    dept = ""
    province_ctx = ""
    dept_fields = {}            # department-level CLOSING DATE / NOTE that apply to all its posts
    post = None
    field = None
    prev_blank = True

    def flush():
        nonlocal post
        if post:
            post["dept"] = post.get("dept") or dept
            post["province_ctx"] = province_ctx
            post["dept_closing"] = dept_fields.get("closing", "")
            for k in ("applications", "attention"):        # department-wide apply instructions
                if not post["fields"].get(k) and dept_fields.get(k):
                    post["fields"][k] = [dept_fields[k]]
            yield_list.append(post)
        post = None

    yield_list = []
    for i, raw in enumerate(lines):
        line = raw.replace("\f", "")
        stripped = line.strip()
        next_blank = (i + 1 >= len(lines)) or not lines[i + 1].strip()

        if not stripped:
            prev_blank = True
            continue
        if PAGE_NO_RE.match(line):
            prev_blank = True
            continue

        m = ANNEX_RE.match(line)
        if m:
            flush(); field = None
            dept, dept_fields = "", {}
            prev_blank = True
            continue
        m = PROVADMIN_RE.match(line)
        if m:
            flush(); field = None
            province_ctx = find_province(title_case(m.group(1)))
            dept, dept_fields = "", {}
            prev_blank = True
            continue
        if SECTION_RE.match(line):
            prev_blank = True
            continue
        # Department heading: an all-caps line standing on its own between blank lines,
        # outside a post's title block.
        if (prev_blank and DEPT_RE.match(line) and not LABEL_RE.match(line)
                and (field not in ("title",)) and stripped == stripped.upper()):
            if len(stripped) < 100 and not stripped.endswith(":"):
                flush(); field = None
                dept = clean_dept(stripped)
                dept_fields = {}
                prev_blank = True
                continue

        m = POST_RE.match(line)
        if m:
            flush()
            post = {"circular": m.group(1), "post_no": m.group(2), "title_lines": [m.group(3)],
                    "fields": {}}
            field = "title"
            prev_blank = False
            continue

        m = LABEL_RE.match(line)
        if m:
            key = FIELD_LABELS[m.group(1).strip()]
            if post is None:
                field = ("dept", key)
                dept_fields[key] = m.group(2)
            else:
                field = key
                post["fields"].setdefault(key, [])
                if post["fields"][key]:
                    post["fields"][key].append("")
                post["fields"][key].append(m.group(2))
            prev_blank = False
            continue

        # continuation line
        if post is not None:
            if field == "title":
                post["title_lines"].append(stripped)
            elif field:
                post["fields"].setdefault(field, []).append(stripped)
        elif isinstance(field, tuple):
            dept_fields[field[1]] = dept_fields.get(field[1], "") + " " + stripped
        prev_blank = False

    flush()
    return yield_list


def build_row(p, circular_no, posted_date, source_url, pdf_url):
    f = {k: join_lines(v) for k, v in p["fields"].items()}
    is_stipend = "stipend" in f and "salary" not in f
    if is_stipend:
        f["salary"] = f["stipend"]
    title_block = [norm_ws(x) for x in p["title_lines"] if norm_ws(x)]
    head = " ".join(title_block)

    # Title = upper-case part of the block, before "REF NO" / "(X n POSTS)".
    caps = []
    for ln in title_block:
        if ln.upper() == ln or not caps:
            caps.append(ln)
        else:
            break
    title_raw = " ".join(caps)
    title_raw = re.split(r"\bREF\.?\s*NO\b", title_raw, flags=re.I)[0]
    title_raw = COUNT_RE.sub("", title_raw)
    title_raw = re.sub(r"\(\s*X\s*\d+\s*$", "", title_raw).strip(" :-,")
    title = title_case(re.sub(r"\s+", " ", title_raw))

    extra_lines = [ln for ln in title_block[len(caps):]]
    count = COUNT_RE.search(head)
    count = int(count.group(1)) if count else 1

    refs = REF_RE.findall(head) or REF_RE.findall(f.get("centre", ""))
    refs = [re.sub(r"\s+", " ", r).strip(" .") for r in refs]
    seen = set()
    refs = [r for r in refs if not (r in seen or seen.add(r))]

    centre = f.get("centre", "")
    centre_clean = "; ".join(norm_ws(x) for x in p["fields"].get("centre", []) if norm_ws(x))
    centre_clean = REF_RE.sub("", centre_clean)
    centre_clean = COUNT_RE.sub("", centre_clean)
    centre_clean = re.sub(r"\(\s*X\s*\d+\s*POSTS?\s*\)|\(\s*\d+\s*POSTS?\s*\)", "", centre_clean, flags=re.I)
    centre_clean = re.sub(r"\s*:\s*(?=\s|$)", " ", centre_clean)
    centre_clean = re.sub(r"\s*;\s*", "; ", norm_ws(centre_clean))
    centre_clean = re.sub(r"(;\s*)+", "; ", centre_clean).strip(" ,;:")
    if len(centre_clean) > 140:
        centre_clean = centre_clean[:137].rsplit(" ", 1)[0] + "…"

    dept = p.get("dept") or "Public Service"
    province = find_province(centre, p.get("province_ctx", ""), f.get("applications", ""),
                             default=p.get("province_ctx", ""))
    if p.get("province_ctx"):
        employer = dept if dept.lower().startswith(p["province_ctx"].lower()) else f"{dept} ({p['province_ctx']})"
    else:
        employer = dept

    closing = parse_date(f.get("closing", "")) or parse_date(p.get("dept_closing", ""))
    if not closing and posted_date:      # no date anywhere: assume the usual ~3 weeks, never "open forever"
        closing = (datetime.date.fromisoformat(posted_date) + datetime.timedelta(days=21)).isoformat()

    # about_role: short intro lines + how to apply + post-specific note. ENQUIRIES is left out on purpose.
    about = []
    intro = join_lines(extra_lines)
    if intro:
        about.append(intro)
    if count > 1:
        about.append(f"Number of posts: {count}")
    if refs:
        about.append("Reference number" + ("s" if len(refs) > 1 else "") + " to quote: " + ", ".join(refs))
    if f.get("applications"):
        about.append("How to apply: " + f["applications"])
    if f.get("attention"):
        about.append("For attention: " + f["attention"])
    if f.get("note"):
        about.append("Note: " + f["note"])
    if closing:
        cl_txt = f.get("closing") or p.get("dept_closing", "")
        about.append("Closing date: " + norm_ws(cl_txt))
    about.append("Apply on the new Z83 form with a detailed CV, quoting the reference number. "
                 f"Full advert: DPSA Public Service Vacancy Circular {circular_no} of "
                 f"{posted_date[:4] if posted_date else ''}.".strip())

    apply_url = pdf_url
    m = re.search(r"(https?://[^\s,;)]+|www\.[^\s,;)]+)", f.get("applications", ""))
    if m:
        u = m.group(1).rstrip(".")
        apply_url = u if u.startswith("http") else "https://" + u

    psv_id = f"PSV-{posted_date[:4] or 'X'}-{circular_no}-{int(p['post_no']):02d}"
    row = {
        "id": psv_id,
        "job_title": title,
        "employer": employer,
        "category": "Internship" if is_stipend else guess_category(title, dept),
        "province": province or "National",
        "location": centre_clean,
        "employment_type": "Internship" if is_stipend else employment_type(head + " " + f.get("salary", "")),
        "salary": norm_ws(f.get("salary", ""))[:160],
        "posted_date": posted_date,
        "closing_date": closing,
        # The site uses reference_no as the page id, so it must be short, unique and URL-safe.
        # The department's own reference numbers (what applicants must quote) are in about_role.
        "reference_no": psv_id,
        "about_role": "\n".join(about),
        "responsibilities": f.get("duties", ""),
        "requirements": f.get("requirements", ""),
        "official_apply_url": apply_url,
        "source_url": source_url,
        "featured": "",
        "status": "live",
    }
    return row


def _fill_from_siblings(posts):
    """Some departments state the closing date / how to apply once for a group of posts.
    Give posts that lack them the value most of their department's other posts use."""
    from collections import Counter, defaultdict
    by_dept = defaultdict(list)
    for p in posts:
        by_dept[(p.get("dept"), p.get("province_ctx"))].append(p)
    for group in by_dept.values():
        for key in ("closing", "applications"):
            vals = Counter(join_lines(p["fields"][key]) for p in group if p["fields"].get(key))
            if not vals:
                continue
            common = vals.most_common(1)[0][0]
            for p in group:
                if not p["fields"].get(key) and not (key == "closing" and p.get("dept_closing")):
                    p["fields"][key] = [common]
    return posts


def parse_pdf_text(text, circular_no, posted_date, source_url, pdf_url, dept_hint="", province_hint=""):
    rows = []
    for p in _fill_from_siblings(split_posts(text)):
        if not p.get("dept") and dept_hint:
            p["dept"] = dept_hint
        if not p.get("province_ctx") and province_hint:
            p["province_ctx"] = province_hint
        if not p["fields"].get("requirements") and not p["fields"].get("duties"):
            continue                                  # not a real post (e.g. stray "POST" in a note)
        rows.append(build_row(p, circular_no, posted_date, source_url, pdf_url))
    return rows


def pdf_to_text(path):
    return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True,
                          text=True, check=True).stdout


# ----------------------------------------------------------------- web

def http_get(url, binary=False):
    import requests
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            return r.content if binary else r.text
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def latest_circular_urls(n):
    page = http_get(INDEX_URL)
    links = re.findall(r"href=['\"](/newsroom/psvc/circular-(\d+)-of-(\d{4})/)['\"]", page)
    uniq = {}
    for path, num, yr in links:
        uniq[(int(yr), int(num))] = BASE + path
    return [uniq[k] for k in sorted(uniq, reverse=True)[:n]]


def circular_sections(page_html):
    """Return (circular_no, posted_date, [(name, pdf_url, is_provincial), ...])."""
    title = re.search(r"Circular\s+(\d+)\s+of\s+(\d{4})", page_html)
    circ = title.group(1) if title else ""
    posted = parse_date(re.sub(r"<[^>]+>", " ", (re.search(r"Posting Date:.*?<br", page_html, re.S) or
                                                  re.search(r"Posting Date:.{0,80}", page_html, re.S)).group(0)))
    sections = []
    provincial = False
    for m in re.finditer(r"<h4>(.*?)</h4>|<a href=\"([^\"]+/\d+/[a-z]{1,2}\.pdf)\">(.*?)</a>",
                         page_html, re.S | re.I):
        if m.group(1) is not None:
            provincial = "provincial" in m.group(1).lower()
        else:
            sections.append((html.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip(),
                             urljoin(BASE, m.group(2)), provincial))
    return circ, posted, sections


def scrape(n=CIRCULARS_TO_CHECK):
    rows = []
    for url in latest_circular_urls(n):
        page = http_get(url)
        circ, posted, sections = circular_sections(page)
        print(f"Circular {circ} ({posted}): {len(sections)} sections", file=sys.stderr)
        for name, pdf_url, provincial in sections:
            try:
                data = http_get(pdf_url, binary=True)
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                    tf.write(data)
                text = pdf_to_text(tf.name)
                os.unlink(tf.name)
            except Exception as e:
                print(f"  ! {name}: {e}", file=sys.stderr)
                continue
            dept_hint = "" if provincial else clean_dept(name)
            prov_hint = find_province(name) if provincial else ""
            got = parse_pdf_text(text, circ, posted, url, pdf_url, dept_hint, prov_hint)
            print(f"  {name}: {len(got)} posts", file=sys.stderr)
            rows.extend(got)
            time.sleep(1)
    today = datetime.date.today().isoformat()
    return [r for r in rows if not r["closing_date"] or r["closing_date"] >= today]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="parse a local circular PDF instead of downloading")
    ap.add_argument("--circular", default="", help="circular number for --pdf")
    ap.add_argument("--posted", default="", help="posting date (YYYY-MM-DD) for --pdf")
    ap.add_argument("--dry-run", action="store_true", help="print rows as JSON, don't write the sheet")
    a = ap.parse_args()

    if a.pdf:
        text = pdf_to_text(a.pdf)
        circ = a.circular or (re.search(r"PUBLICATION NO\s+(\d+)", text) or [None, ""])[1]
        posted = a.posted or parse_date((re.search(r"DATE ISSUED\s+(.+)", text) or [None, ""])[1])
        rows = parse_pdf_text(text, circ, posted, INDEX_URL, INDEX_URL)
    else:
        rows = scrape()

    if a.dry_run:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=1)
        print(f"\n{len(rows)} posts", file=sys.stderr)
        return
    import sheet_writer
    wrote = sheet_writer.append_jobs(rows)
    print(f"DPSA: parsed {len(rows)} open posts, wrote {wrote} new rows.", file=sys.stderr)


if __name__ == "__main__":
    main()
